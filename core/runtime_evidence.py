"""Copy observed runtime evidence without manufacturing missing observations."""
from copy import deepcopy


def runtime_evidence(run):
    fields = ('command_results', 'unauthorized_write_detected',
              'unauthorized_files_changed', 'error_events')
    return {key: deepcopy(run[key]) for key in fields if key in run}
