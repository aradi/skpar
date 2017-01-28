"""
"""
import logging
import numpy as np
from skopt.core.utils import get_logger, normalise
from skopt.core.utils import flatten, flatten_two

DEFAULT_GLOBAL_COST_FUNC = "rms"

def abserr(ref, model):
    """Return the per-element difference model and reference.
    """
    rr = np.asarray(ref)
    mm = np.asarray(model)
    assert rr.shape == mm.shape, (rr.shape, mm.shape)
    return mm - ref

def relerr(ref, model):
    """Return the per-element relative difference between model and reference.

    To handle cases where `ref` vanish, and possibly `model` vanish
    at the same time, we:

        * translate directly a vanishing absolute error into vanishing
          relative error (where both `ref` and `model` vanish.

        * take the model as a denominator, thus yielding 1, where
          `ref` vanishes but `model` is non zero
    """
    rr = np.asarray(ref)
    mm = np.asarray(model)
    # get deviations
    err = abserr(rr, mm)
    # fix the denominator
    denom = rr
    denom[rr == 0.] = mm[rr == 0.]
    # assert 0 absolute error even for 0 denominator
    rele = np.zeros(err.shape)
    rele[err != 0] = err[err != 0] / denom[err != 0]
    return rele

def cost_RMS(ref, model, weights, errf=abserr):
    """Return the weighted-RMS deviation"""
    assert np.asarray(ref).shape == np.asarray(model).shape
    assert np.asarray(ref).shape == np.asarray(weights).shape
    err2 = errf(ref, model) ** 2
    rms = np.sqrt(np.sum(weights*err2))
    return rms

def eval_objectives(objectives):
    """
    """
    fitness = np.array([objv() for objv in objectives])
    return fitness

# ----------------------------------------------------------------------
# Function mappers
# ----------------------------------------------------------------------
# use small letters for the function names; make sure
# the input parser coerces any capitalisation in advance

# cost functions
costf = {"rms": cost_RMS, }

# error types
errf = {"abs": abserr, "rel": relerr, "abserr": abserr, "relerr": relerr,}
# ----------------------------------------------------------------------


class Evaluator (object):
    """
    __Evaluator__

    The evaluator is the only thing visible to the optimiser.  
    It has several things to do:  

    1. Accept a list (or dict?) of parameter values (or key-value pairs),
       and an iteration number (or a tuple: (generation,particle_index)).
    2. Update tasks (and underlying models) with new parameter values.
    3. Execute the tasks to obtain model data with the new parameters.
    5. Evaluate fitness for individual objectives.
    6. Evaluate global fitness (cost) and return the value. It may be 
       good to also return the max error, to be used as a stopping criterion.
    """   
    def __init__(self, objectives, tasks, costf=costf[DEFAULT_GLOBAL_COST_FUNC],
                 utopia = None,
                 verbose=False, logger=logging.getLogger(__name__), **kwargs):
        self.objectives = objectives
        self.weights = normalise([oo.weight for oo in objectives])
        self.tasks = tasks
        self.costf = costf
        if utopia is None:
            self.utopia = np.zeros(len(self.objectives))
        else:
            assert len(utopia) == len(objectives), (len(utopia), len(objectives))
            self.utopia = utopia
        self.verbose = verbose
        self.logger = logger
    
    def evaluate(self, parameters, iteration=None):
        """Evaluate the global fitness of a given point in parameter space.

        This is the only object accessible to the optimiser.

        Args:
            parameters (list or dict): current point in design/parameter space
            iteration: (int or tupple): current iteration or current 
                generation and individual index within generation

        Return:
            fitness (float): global fitness of the current design point
        """
        # Update models with new parameters.
        # Updating the models should be the first task in the tasks list,
        # but user may decide to omit it in some situations (e.g. if only
        # interested in evaluating the set of models, not optimising).
        jj = 0
        task = self.tasks[0]
        try:
            task(parameters, iteration)
            jj = 1
        except TypeError:
            # assume we don't have parameter update for some reason
            # and TypeError is due to task not accepting arguments
            pass
        except:
            self.logger.critical('\nEvaluation FAILED at task {}:\n{}'.format(jj, task))
            raise
        # Get new model data
        for ii, task in enumerate(self.tasks[jj:]):
            kk = ii + jj
            try:
                task()
            except:
                self.logger.critical('\nEvaluation FAILED at task {}:\n{}'.format(kk+1, task))
                raise
        # Evaluate individual fitness for each objective
        self.objvfitness = eval_objectives(self.objectives)
        ref = self.utopia
        # evaluate global fitness
        cost = self.costf(ref, self.objvfitness, self.weights)
        return np.atleast_1d(cost)

    def __call__(self, parameters, iteration=None):
        return self.evaluate(parameters, iteration)


# ----------------------------------------------------------------------
# OLD SKOPT... soon to be removed
# ----------------------------------------------------------------------
def calcErrors(ref, calc):
        """
        Takes calc, and ref, which are lists or 1D numpy arrays of the same length,
        containing the calculated and the reference data, respectively, and
        returns two arrays: error (deviation), and relative error.
        In case that ref contains 0, the relative error is patched to 1 (i.e. 100%)
        """
        cc = np.asarray(calc); rr = np.asarray(ref)
        err = cc - rr
        relerr = (cc - rr)/rr
        relerr[relerr==np.inf] = 1. # suppose we get 0 as a reference data
        return err, relerr
        
    
def calcCost (errors=None, weights=None, 
              calc=None, ref=None, 
              useRelErr=False, normalise=True):
        """
        Calculate the cost or fitness given either precomputed errors or the 
        calculated(calc) and reference(ref) data. In either case, weight the 
        errors by the weights.
        weights, and errors, or calc and ref, are lists or 1D numpy arrays of 
        the same length, weights are optional, but either errors, or calc and 
        ref has to be supplied.
        if calc and ref are given, then the error used in the cost evaluation is 
        either absolute, or relative, as per the useRelErr flag.
        weights are normalised here, if their sum does not evaluate to 1.
        """
        # permit the function to be called either with data/ref or directly w/ errors
        if errors is None:
            deviation,relerr = calcErrors(ref, calc)
            if useRelErr:
                err = relerr
            else:
                err = deviation
        else:
            err = np.asarray(errors)
            
        # assign equal weights if not specified otherwise            
        if weights is None:
            ww = np.ones(len(err))
        else:
            ww = np.asarray(weights)
            
        assert len(weights) == len(err)
            
        # normalise the weights if not already done so
        norm = np.sum(ww)
        assert not np.allclose(norm,0.0)
        
        if normalise and not np.allclose(norm,1.0):
            ww = ww/norm
            
        # cost becomes the sum of weighted sqared errors
        # i.e. RMS value in case of absolute deviation and identical weights
        wr2 = ww*np.square(err)
        cost = np.sqrt(np.sum(wr2))
        
        return cost
    
    
def reportError (ref, calc, err, relerr, keys=None, log=logging.getLogger(__name__)):
    """
    Report to the logger, in a neat tabular format, the reference value, 
    the calculated value, the absolute error and the relative error in %.
    If keys list is supplied, it should have the same length as ref.
    Keys should contain ascii names of the values in ref.
    If keys contain '-', no values will be reported for the corresponding
    datum in ref. 
    Not supplying keys leads to full report without data names.
    """
    log.info('{k:<20s}{r:>10s}{c:>10s}{ea:>10s}{er:>10s}'.
             format(k='Datum',r='Ref.',c='Calc.',ea='Deviation',er='% Err'))
    log.info('============================================================')
    if keys is None:
        keys = ['']*len(ref)
    for i,key in enumerate(keys):
        if key!='-':    
            log.info('{k:20s}{r:10.3f}{c:10.3f}{ea:10.3f}{er:10.1f}'.
            format(k=key,r=ref[i],c=calc[i],ea=err[i],er=relerr[i]*100))
    
    
def normaliseWeights(weights):
    """
    normalise weights so that their sum evaluates to 1
    """
    return np.asarray(weights)/np.sum(np.asarray(weights))


class EvaluateCost (object):
    r"""
    ### Cost Function

    The following cost function is applied in the context of ETB fitting 
    to DFT reference data.  
    See the manual of nanoSKIF v1.0 from NanoAcademic Technologies.
    Assumed is that reference band-structure data is available for multiple systems,
    identified by index $s$.    
    Bandstructure data is seen as a collection of band and k points identified 
    by indexes $b$ and $k$.  
    Therefore, each (band,k-pt) pair is given a weight $\omega_{b,k}$.   
    Each system is assigned a weight $\omega_s$.  
    The cost function reads:  

    $f(\{\lambda_i\}) = 
    \sqrt{\sum_s{\omega_s}\sum_{b,k}
    {\omega_{s,b,k}\left(\varepsilon_{s,b,k}(\{\lambda_i\}) -
    \varepsilon_{s,b,k}^{\rm ref}\right)^2}}$,

    where $\{\lambda_i\}$ denotes the parameter vector, and $\varepsilon$
    denotes the energy of a given $(b,k)$ point.


    Note that the dimensionality $b\times k$ need not be the same accross systems.  
    Note further, that weights are normalised, e.g. $\sum{\omega} = 1$.

    The above is nicely formulated where we have similar systems, with similar 
    number of $(E,k)$ points.  
    But if we include dissimilar systems, e.g. bulk semiconductor and bulk oxide,
    largely differing by their lattices and by the number of $(E,k)$ reference points,
    and if we further want to include effective masses as targets, then it would 
    be simpler, I think, to reformulate the cost function to somewhat more general:

    $f(\{\lambda_i\}) = 
    \sqrt{\sum_s{\omega_s}\sum_{j}
    {\omega_{s,j}\left(\upsilon_{s,j}(\{\lambda_i\}) - \upsilon_{s,j}^{\rm ref}\right)^2}}$,

    where the $\{\upsilon_j\}$ encompasses the space of values corresponding 
    to $(b,k)$ points (now linearly indexed), or effective masses, or certain gaps,
    or $k$-position of certain band extrema, etc.

    One can go a step further and dispence of the $system$, and span $j$ over all 
    computed/reference values for all atomic systems in consideration.


    In making the error evaluation function a class we gain the following:
    * we can create a different instance of the error evaluator with
      different logging verbosity, and data key list of the reported
      values, for each system, and select different error function
    * the above properties can be tailored upon instantiation
    """
    def __init__(self, refdata=None, weights=None,
                 evalerr=None, evalcost=None, useRelErr=False,
                 verbose=True, reporterr=None, reportkeys = None, 
                 normaliseweights=True,
                 log=logging.getLogger(__name__)):
        self.ref = refdata or [],
        self.weights = weights or []
        self.evalerr = evalerr or calcErrors
        self.evalcost = evalcost or calcCost
        self.useRelErr = useRelErr
        self.verbose = verbose
        self.report = reporterr or reportError
        self.keys = reportkeys
        self.normaliseweights = normaliseweights
        self.log = log
        
    def __call__ (self, calc, ref=None, weights=None):
        """
        calculate residues and relative error and log info if verbose
        calculate and return cost/fitness
        """
        if ref is None:
            ref = self.ref
        if weights is None:
            weights = self.weights
            
        assert len(calc) == len(ref)
        assert len(weights) == len(ref)
            
        err, relerr = self.evalerr(ref, calc)
        self.err = err
        self.relerr = relerr
        
        if self.verbose:
            self.report(ref, calc, err, relerr, 
                        keys=self.keys, log=self.log)
            
        if self.useRelErr:
            self.err = relerr
        else:
            self.err = err
            
        self.maxerr = np.max(np.abs(self.err))
        self.maxrelerr = np.max(np.abs(self.relerr))

        self.cost = self.evalcost(errors=self.err, weights=weights,
                            normalise=self.normaliseweights)
        
        return self.cost


class Evaluator_OLD (object):
    """
    ### Evaluator

    The evaluator is the only thing visible to the optimiser.  
    It has several things to do:  

    1. Take a list of parameter values, and iteration number 
        (tuple: (generation,particle_index)).
    2. Update files that drive the calculators with new parameters
    3. Run the calculators, log the results tagged somehow by iteration number
    4. Run the analysers
    5. Combine the resulting data in a list of the same character as the reference data
    6. Evaluate fitness (cost) and return the value, return also max error that
       can be used as a stopping criterion

    Ideally, the evaluator does not know anything about the parameters itself, 
    neither does the optimiser, obviously -- just a set of numbers.  
    However, the parameters are a list, so someone else knows how to handle them, 
    and this someone should be made known to the evaluator instance.  
    This possibly makes it convenient to abstract a System layer. 
    So, what is a system?

    * a collection of atoms, with its own directory for calculations  
    * a dictionary with the data resulting from calculators (executable)
    * a dictionary with the data resulting from analysers (postprocessing)  
    * a tasklist with
        1. calculators  
        2. analysers   
        3. plotter  (optional)
    * parameter handler
    ...
    """   
    def __init__(self, systems, systemweights = None,  
                 workdir='./', 
                 costfunc=None, verbose=True, useRelErr=False,
                 skipexecution=False,
                 log=logging.getLogger(__name__),**kwargs):
        self.workdir = workdir
        self.systems = systems
        self.log = log
        self.setFlatRefAndWeights(systemweights)
#        self.updateRefData()
        self.evalcost = costfunc or\
                        EvaluateCost(useRelErr=useRelErr,
                                     verbose=verbose,
                                     log=log,**kwargs)
        self.skipexecution=skipexecution
    
    
    def setFlatRefAndWeights(self, systemweights):
        """
        The reference data and weights of a sytem are 
        assumed dictionaries belonging to the system, so
        here we build up two flat lists that represent 
        the reference data and weights for all systems
        """
        # set systemweights if not supplied already
        # we need a list of the length of self.systems.
        # if a dictionary is supplied we transform it.
        # an ordered dictionary may be more manageable 
        # if we deal with many systems... unlikely
        if systemweights is not None:
            try:
                assert isinstance(systemweights, list)
                assert len(systemweights) == len(self.systems)
                self.systemweights = systemweights
            except AssertionError:
                assert isinstance(systemweights,dict)
                self.systemweights =\
                    [systemweights[ss.name] for ss in self.systems]
        else:
            self.systemweights = [1.0/len(self.systems)]*len(self.systems)
            self.log.info('Default systems weights will be used:\n{0}'.
                     format(self.systemweights))
        assert self.systemweights is not None

        # setout a flat list of weights, and corresponding reference data
        self.flatweights = []
        self.flatrefdata = []
        for ss,sw in zip(self.systems,self.systemweights):
            if not np.allclose(sw,0.0,1.e-12):
                ref, weights = list(zip(*flatten_two(ss.refdata,ss.weights)))
                weights = np.asarray(weights)*sw
                self.flatweights.extend(weights)
                self.flatrefdata.extend(ref)
                self.log.debug('Flattened refdata and weights for system {0}'.
                                format(ss.name))
        
        
    def evaluate(self, parameters, iteration=None):
        """
        The only things that the optimiser passes to the evaluator are
        1) the updated values of the parameters (list), and 
        2) the current iteration (tupple: e.g. (geration,particle), in 
            case of PSO.
        """
        self.flatcalcdata = []
        for ss,sw in zip(self.systems,self.systemweights):
            if not self.skipexecution:
                ss.update(ss, parameters=parameters, iteration=iteration)
                self.log.debug('Executing system {0}.'.format(ss.name))
                ss.execute()
                self.log.debug('...done with system {0}.'.format(ss.name))
            if not np.allclose(sw,0.0,1.e-12):
                self.log.debug('Flattening calculated data for system {0}...'.
                                format(ss.name))
                ref,calc = list(zip(*flatten_two(ss.refdata,ss.calculated)))
                self.flatcalcdata.extend(calc)
                self.log.debug('\t...done.')
        assert len(self.flatcalcdata) == len(self.flatrefdata)
        self.log.info('Evaluating cost function...')
        self.cost = self.evalcost(self.flatcalcdata, self.flatrefdata, self.flatweights)
        self.log.info('============================================================')
        self.log.info('Cost at iteration {0} is: {1}'.format(iteration, self.cost))
        self.log.info('')
        return self.cost 
    
    def __call__(self,parameters,iteration=None):
        return self.evaluate(parameters,iteration)