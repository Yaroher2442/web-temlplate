SCHEDULER_ENABLE = False

try:
    from apscheduler.schedulers import SchedulerNotRunningError

    SCHEDULER_ENABLE = True
except ImportError:
    pass

DEBUG = False
METRICS_ENABLE = False
