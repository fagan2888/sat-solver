from attr import attr, attributes, Factory, asdict
from attr.validators import instance_of
from enum import Enum

from .constraints import Requirement


class JobType(Enum):
    install = 1
    remove = 2
    update = 3


@attributes
class _Job(object):
    requirement = attr(validator=instance_of(Requirement))
    kind = attr(validator=instance_of(JobType))


@attributes
class AdhocConstraints(object):
    allow_newer = attr(default=Factory(set))
    allow_any = attr(default=Factory(set))
    allow_older = attr(default=Factory(set))

    def asdict(self):
        return asdict(self)

    @property
    def targets(self):
        return set.union(self.allow_newer, self.allow_any, self.allow_older)


class Request(object):
    def __init__(self):
        self.jobs = []
        self.adhoc_constraints = AdhocConstraints()

    def install(self, requirement):
        self._add_job(requirement, JobType.install)

    def remove(self, requirement):
        self._add_job(requirement, JobType.remove)

    def update(self, requirement):
        self._add_job(requirement, JobType.update)

    def allow_newer(self, package_name):
        self.adhoc_constraints.allow_newer.add(package_name)

    def allow_any(self, package_name):
        self.adhoc_constraints.allow_any.add(package_name)

    def allow_older(self, package_name):
        self.adhoc_constraints.allow_older.add(package_name)

    def _add_job(self, requirement, job_type):
        self.jobs.append(_Job(requirement, job_type))
