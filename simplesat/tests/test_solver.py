import io
import unittest

from okonomiyaki.versions import EnpkgVersion

from simplesat.constraints import PrettyPackageStringParser, InstallRequirement
from simplesat.dependency_solver import (
    DependencySolver, requirements_are_satisfiable,
    requirements_from_repository, repository_from_requirements,
    repository_is_consistent, requirements_are_complete,
)
from simplesat.errors import MissingInstallRequires, SatisfiabilityError
from simplesat.pool import Pool
from simplesat.repository import Repository
from simplesat.request import Request
from simplesat.test_utils import Scenario
from simplesat.transaction import (
    InstallOperation, RemoveOperation, UpdateOperation
)


R = InstallRequirement._from_string
P = PrettyPackageStringParser(EnpkgVersion.from_string).parse_to_package


class TestSolver(unittest.TestCase):
    def setUp(self):
        self.repository = Repository()
        self.installed_repository = Repository()

        self._package_parser = PrettyPackageStringParser(
            EnpkgVersion.from_string
        )

    def package_factory(self, s):
        return self._package_parser.parse_to_package(s)

    def resolve(self, request, strict=False):
        pool = Pool([self.repository, self.installed_repository])
        solver = DependencySolver(
            pool, self.repository, self.installed_repository,
            use_pruning=False, strict=strict
        )
        return solver.solve(request)

    def assertEqualOperations(self, operations, r_operations):
        self.assertEqual(operations, r_operations)

    def test_simple_install(self):
        # Given
        mkl = self.package_factory(u"mkl 10.3-1")
        self.repository.add_package(mkl)

        r_operations = [InstallOperation(mkl)]

        request = Request()
        request.install(R("mkl"))

        # When
        transaction = self.resolve(request)

        # Then
        self.assertEqualOperations(transaction.operations, r_operations)

    def test_multiple_installs(self):
        # Given
        mkl = self.package_factory(u"mkl 10.3-1")
        libgfortran = self.package_factory(u"libgfortran 3.0.0-2")

        r_operations = [
            InstallOperation(libgfortran),
            InstallOperation(mkl),
        ]

        self.repository.add_package(mkl)
        self.repository.add_package(libgfortran)

        request = Request()
        request.install(R("mkl"))
        request.install(R("libgfortran"))

        # When
        transaction = self.resolve(request)

        # Then
        self.assertEqualOperations(transaction.operations, r_operations)

    def test_simple_dependency(self):
        # Given
        mkl = self.package_factory(u"mkl 10.3-1")
        libgfortran = self.package_factory(u"libgfortran 3.0.0-2")
        numpy = self.package_factory(
            u"numpy 1.9.2-1; depends (mkl == 10.3-1, libgfortran ^= 3.0.0)"
        )

        r_operations = [
            # libgfortran sorts before mkl
            InstallOperation(libgfortran),
            InstallOperation(mkl),
            InstallOperation(numpy),
        ]

        self.repository.add_package(mkl)
        self.repository.add_package(libgfortran)
        self.repository.add_package(numpy)

        request = Request()
        request.install(R("numpy"))

        # When
        transaction = self.resolve(request)

        # Then
        self.assertEqualOperations(transaction.operations, r_operations)

    def test_already_installed(self):
        # Given
        mkl1 = self.package_factory(u"mkl 10.3-1")
        mkl2 = self.package_factory(u"mkl 10.3-2")

        r_operations = []

        self.repository.add_package(mkl1)
        self.repository.add_package(mkl2)
        self.installed_repository.add_package(mkl1)

        # When
        request = Request()
        request.install(R("mkl"))

        transaction = self.resolve(request)

        # Then
        self.assertEqualOperations(transaction.operations, r_operations)

        # Given
        r_operations = [
            RemoveOperation(mkl1),
            InstallOperation(mkl2),
        ]
        r_pretty_operations = [
            UpdateOperation(mkl2, mkl1),
        ]

        # When
        request = Request()
        request.install(R("mkl > 10.3-1"))

        # When
        transaction = self.resolve(request)

        # Then
        self.assertEqualOperations(transaction.operations, r_operations)
        self.assertEqualOperations(
            transaction.pretty_operations, r_pretty_operations)

    def test_requirements_are_satisfiable(self):
        # Given
        scenario = Scenario.from_yaml(io.StringIO(u"""
                packages:
                    - MKL 10.2-1
                    - MKL 10.3-1
                    - numpy 1.7.1-1; depends (MKL == 10.3-1)
                    - numpy 1.8.1-1; depends (MKL == 10.3-1)

                request:
                    - operation: "install"
                      requirement: "numpy"
        """))
        repositories = scenario.remote_repositories
        requirements = [job.requirement for job in scenario.request.jobs]

        # When
        result = requirements_are_satisfiable(repositories, requirements)

        # Then
        self.assertTrue(result)

    def test_requirements_are_not_satisfiable(self):
        # Given
        scenario = Scenario.from_yaml(io.StringIO(u"""
            packages:
                - MKL 10.2-1
                - MKL 10.3-1
                - numpy 1.7.1-1; depends (MKL == 10.3-1)
                - numpy 1.8.1-1; depends (MKL == 10.3-1)

            request:
                - operation: "install"
                  requirement: "numpy"
                - operation: "install"
                  requirement: "MKL != 10.3-1"
        """))
        repositories = scenario.remote_repositories
        requirements = [job.requirement for job in scenario.request.jobs]

        # When
        result = requirements_are_satisfiable(repositories, requirements)

        # Then
        self.assertFalse(result)

    def test_requirements_are_complete(self):
        # Given
        scenario = Scenario.from_yaml(io.StringIO(u"""
            packages:
                - MKL 10.3-1
                - numpy 1.8.1-1; depends (MKL == 10.3-1)

            request:
                - operation: install
                  requirement: numpy ^= 1.8.1
                - operation: install
                  requirement: MKL == 10.3-1
        """))
        repositories = scenario.remote_repositories

        # When
        requirements = [job.requirement for job in scenario.request.jobs]
        result = requirements_are_complete(repositories, requirements)

        # Then
        self.assertTrue(result)

    def test_requirements_are_not_complete(self):
        # Given
        scenario = Scenario.from_yaml(io.StringIO(u"""
            packages:
                - MKL 10.3-1
                - numpy 1.8.1-1; depends (MKL == 10.3-1)

            request:
                - operation: install
                  requirement: numpy
        """))
        repositories = scenario.remote_repositories

        # When
        requirements = [job.requirement for job in scenario.request.jobs]
        result = requirements_are_complete(repositories, requirements)

        # Then
        self.assertFalse(result)

    def test_repository_from_requirements(self):
        # Given
        requirements = (
            R(u'MKL == 10.3-1'),
            R(u'numpy == 1.9.1-1'),
            R(u'numpy == 1.9.1-2'),
            R(u'numpy == 1.9.1-3'),
        )
        expected = (
            P(u'MKL 10.3-1'),
            P(u'numpy 1.9.1-1; depends (MKL == 10.3-1)'),
            P(u'numpy 1.9.1-2; depends (MKL)'),
            P(u'numpy 1.9.1-3'),
        )

        # When
        repositories = [Repository(expected)]
        repository = repository_from_requirements(repositories, requirements)

        # Then
        result = tuple(repository)
        self.assertEqual(result, expected)

    def test_requirements_from_repository(self):
        # Given
        packages = (
            P(u'MKL 10.3-1'),
            P(u'numpy 1.9.1-1; depends (MKL == 10.3-1)'),
            P(u'numpy 1.9.1-2; depends (MKL)'),
            P(u'numpy 1.9.1-3'),
        )
        expected = (
            R(u'MKL == 10.3-1'),
            R(u'numpy == 1.9.1-1'),
            R(u'numpy == 1.9.1-2'),
            R(u'numpy == 1.9.1-3'),
        )

        # When
        repository = Repository(packages)
        result = requirements_from_repository(repository)

        # Then
        self.assertEqual(result, expected)

    def test_repository_is_consistent(self):
        # Given
        scenario = Scenario.from_yaml(io.StringIO(u"""
            packages:
                - MKL 10.3-1
                - numpy 1.8.1-1; depends (MKL == 10.3-1)
        """))

        # When
        repository = scenario.remote_repositories[0]
        result = repository_is_consistent(repository)

        # Then
        self.assertTrue(result)

    def test_repository_is_not_consistent(self):
        # Given
        scenario = Scenario.from_yaml(io.StringIO(u"""
            packages:
                - numpy 1.8.1-1; depends (MKL == 10.3-1)
        """))

        # When
        repository = scenario.remote_repositories[0]
        result = repository_is_consistent(repository)

        # Then
        self.assertFalse(result)

    def test_missing_direct_dependency_fails(self):
        # Given
        numpy192 = self.package_factory(u"numpy 1.9.2-1")
        numpy200 = self.package_factory(u"numpy 2.0.0-1; depends (missing)")

        self.repository.add_package(numpy192)
        self.repository.add_package(numpy200)

        # When
        request = Request()
        request.install(R("numpy >= 2.0"))

        # Then
        with self.assertRaises(SatisfiabilityError):
            self.resolve(request)

    def test_missing_indirect_dependency_fails(self):
        # Given
        mkl = self.package_factory(u"MKL 10.3-1; depends (MISSING)")
        numpy192 = self.package_factory(u"numpy 1.9.2-1")
        numpy200 = self.package_factory(u"numpy 2.0.0-1; depends (MKL)")

        self.repository.add_package(mkl)
        self.repository.add_package(numpy192)
        self.repository.add_package(numpy200)

        # When
        request = Request()
        request.install(R("numpy >= 2.0"))

        # Then
        with self.assertRaises(SatisfiabilityError):
            self.resolve(request)

    def test_strange_key_error_bug_on_failure(self):
        # Given
        mkl = self.package_factory(u'MKL 10.3-1')
        libgfortran = self.package_factory(u'libgfortran 3.0.0-2')
        numpy192 = self.package_factory(
            u"numpy 1.9.2-1; depends (libgfortran ^= 3.0.0, MKL == 10.3-1)")
        numpy200 = self.package_factory(
            u"numpy 2.0.0-1; depends (nonexistent)")
        request = Request()

        # When
        for pkg in (mkl, libgfortran, numpy192, numpy200):
            self.repository.add_package(pkg)
        request.install(R("numpy >= 2.0"))

        # Then
        with self.assertRaises(SatisfiabilityError):
            self.resolve(request)

    def test_missing_dependency_strict(self):
        # Given
        mkl = self.package_factory(u'MKL 10.3-1')
        libgfortran = self.package_factory(u'libgfortran 3.0.0-2')
        numpy192 = self.package_factory(
            u"numpy 1.9.2-1; depends (libgfortran ^= 3.0.0, MKL == 10.3-1)")
        numpy200 = self.package_factory(
            u"numpy 2.0.0-1; depends (nonexistent)")
        request = Request()

        # When
        for pkg in (mkl, libgfortran, numpy192, numpy200):
            self.repository.add_package(pkg)
        request.install(R("numpy == 2.0.0-1"))

        # Then
        with self.assertRaises(MissingInstallRequires):
            self.resolve(request, strict=True)
