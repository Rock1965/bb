"""Code common to the various python bb commands"""

import logging
import os
import sys
import warnings

PATH = os.getenv('PATH').split(':')
bitbake_paths = [os.path.join(path, '..', 'lib')
                 for path in PATH if os.path.exists(os.path.join(path, 'bitbake'))]
if not bitbake_paths:
    raise ImportError("Unable to locate bitbake, please ensure PATH is set correctly.")

sys.path[0:0] = bitbake_paths

import bb.msg
import bb.utils
import bb.providers
import bb.tinfoil


class Terminate(BaseException):
    pass


class Tinfoil(bb.tinfoil.Tinfoil):
    def __init__(self, output=sys.stdout):
        # Needed to avoid deprecation warnings with python 2.6
        warnings.filterwarnings("ignore", category=DeprecationWarning)

        # Set up logging
        self.logger = logging.getLogger('BitBake')
        setup_logger(self.logger, output)

        initialenv = os.environ.copy()
        bb.utils.clean_environment()
        self.config = bb.tinfoil.TinfoilConfig(parse_only=True)
        self.cooker = bb.cooker.BBCooker(self.config, self.register_idle_function,
                                         initialenv)
        self.config_data = self.cooker.configuration.data
        bb.providers.logger.setLevel(logging.ERROR)
        bb.taskdata.logger.setLevel(logging.CRITICAL)
        self.cooker_data = None
        self.taskdata = None

    def prepare_taskdata(self, provided=None, rprovided=None):
        self.cache_data = self.cooker.status

        self.localdata = bb.data.createCopy(self.config_data)
        self.localdata.finalize()
        # TODO: why isn't expandKeys a method of DataSmart?
        bb.data.expandKeys(self.localdata)

        if self.taskdata is None:
            self.taskdata = bb.taskdata.TaskData(abort=False)

        if provided:
            self.add_provided(provided)

        if rprovided:
            self.add_rprovided(rprovided)

    def add_rprovided(self, rprovided):
        for item in rprovided:
            self.taskdata.add_rprovider(self.localdata, self.cache_data, item)

        self.taskdata.add_unresolved(self.localdata, self.cache_data)

    def add_provided(self, provided):
        if 'world' in provided:
            if not self.cache_data.world_target:
                self.cooker.buildWorldTargetList()
            provided.remove('world')
            provided.extend(self.cache_data.world_target)

        if 'universe' in provided:
            provided.remove('universe')
            provided.extend(self.cache_data.universe_target)

        for item in provided:
            self.taskdata.add_provider(self.localdata, self.cache_data, item)

        self.taskdata.add_unresolved(self.localdata, self.cache_data)

    def rec_get_dependees(self, targetid, depth=0, seen=None):
        if seen is None:
            seen = set()

        for dependee_fnid, dependee_id in self.get_dependees(targetid, seen):
            yield dependee_id, depth

            for _id, _depth in self.rec_get_dependees(dependee_id, depth+1, seen):
                yield _id, _depth

    def get_dependees(self, targetid, seen):
        fnid = self.taskdata.build_targets[targetid][0]
        dep_fnids = self.taskdata.get_dependees(targetid)
        for dep_fnid in dep_fnids:
            if dep_fnid in seen:
                continue
            seen.add(dep_fnid)
            for target in self.taskdata.build_targets:
                if dep_fnid in self.taskdata.build_targets[target]:
                    yield dep_fnid, target


def setup_logger(logger, output=sys.stderr):
    log_format = bb.msg.BBLogFormatter("%(levelname)s: %(message)s")
    if output.isatty():
        log_format.enable_color()
    console = logging.StreamHandler(output)
    console.setFormatter(log_format)

    bb.msg.addDefaultlogFilter(console)
    logger.addHandler(console)
    logger.setLevel(logging.INFO)


def sigterm_exception(signum, stackframe):
    raise Terminate()


def run_main(main):
    import signal
    signal.signal(signal.SIGTERM, sigterm_exception)
    try:
        sys.exit(main(sys.argv[1:]) or 0)
    except KeyboardInterrupt:
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        os.kill(os.getpid(), signal.SIGINT)
    except Terminate:
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        os.kill(os.getpid(), signal.SIGTERM)