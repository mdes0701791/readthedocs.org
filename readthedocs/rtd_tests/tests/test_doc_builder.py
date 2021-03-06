# -*- coding: utf-8 -*-
from __future__ import (
    absolute_import, division, print_function, unicode_literals)

import os
import tempfile
from collections import namedtuple

import mock
import py
import pytest
import yaml
from django.test import TestCase
from django.test.utils import override_settings
from django_dynamic_fixture import get
from mock import patch

from readthedocs.builds.models import Version
from readthedocs.doc_builder.backends.mkdocs import BaseMkdocs, MkdocsHTML
from readthedocs.doc_builder.backends.sphinx import BaseSphinx
from readthedocs.doc_builder.python_environments import Virtualenv
from readthedocs.projects.exceptions import ProjectConfigurationError
from readthedocs.projects.models import Project


class SphinxBuilderTest(TestCase):

    fixtures = ['test_data']

    def setUp(self):
        self.project = Project.objects.get(slug='pip')
        self.version = self.project.versions.first()

        self.build_env = namedtuple('project', 'version')
        self.build_env.project = self.project
        self.build_env.version = self.version

        BaseSphinx.type = 'base'
        BaseSphinx.sphinx_build_dir = tempfile.mkdtemp()

    @patch(
        'readthedocs.doc_builder.backends.sphinx.SPHINX_TEMPLATE_DIR',
        '/tmp/sphinx-template-dir',
    )
    @patch('readthedocs.doc_builder.backends.sphinx.BaseSphinx.docs_dir')
    @patch('readthedocs.doc_builder.backends.sphinx.BaseSphinx.create_index')
    @patch('readthedocs.doc_builder.backends.sphinx.BaseSphinx.get_config_params')
    @patch('readthedocs.doc_builder.backends.sphinx.BaseSphinx.run')
    @patch('readthedocs.builds.models.Version.get_conf_py_path')
    @patch('readthedocs.projects.models.Project.checkout_path')
    def test_create_conf_py(
            self, checkout_path, get_conf_py_path, _,
            get_config_params, create_index, docs_dir):
        """
        Test for a project without ``conf.py`` file.

        When this happen, the ``get_conf_py_path`` raises a
        ``ProjectConfigurationError`` which is captured by our own code and
        generates a conf.py file based using our own template.

        This template should be properly rendered in Python2 and Python3 without
        any kind of exception raised by ``append_conf`` (we were originally
        having a ``TypeError`` because of an encoding problem in Python3)
        """
        tmp_dir = tempfile.mkdtemp()
        checkout_path.return_value = tmp_dir 
        docs_dir.return_value = tmp_dir
        create_index.return_value = 'README.rst'
        get_config_params.return_value = {}
        get_conf_py_path.side_effect = ProjectConfigurationError
        python_env = Virtualenv(
            version=self.version,
            build_env=self.build_env,
            config=None,
        )
        base_sphinx = BaseSphinx(
            build_env=self.build_env,
            python_env=python_env,
        )
        try:
            base_sphinx.append_conf()
        except Exception:
            pytest.fail('Exception was generated when append_conf called.')

        # Check the content generated by our method is the same than what we
        # expects from a pre-generated file
        generated_conf_py = os.path.join(base_sphinx.docs_dir(), 'conf.py')
        expected_conf_py = os.path.join(
            os.path.dirname(__file__),
            '..',
            'files',
            'conf.py'
        )
        with open(generated_conf_py) as gf, open(expected_conf_py) as ef:
            autogenerated_confpy_lines = 28
            self.assertEqual(
                gf.readlines()[:autogenerated_confpy_lines],
                ef.readlines()[:autogenerated_confpy_lines]
            )

    @patch(
        'readthedocs.doc_builder.backends.sphinx.SPHINX_TEMPLATE_DIR',
        '/tmp/sphinx-template-dir',
    )
    @patch('readthedocs.doc_builder.backends.sphinx.BaseSphinx.docs_dir')
    @patch('readthedocs.doc_builder.backends.sphinx.BaseSphinx.create_index')
    @patch('readthedocs.doc_builder.backends.sphinx.BaseSphinx.get_config_params')
    @patch('readthedocs.doc_builder.backends.sphinx.BaseSphinx.run')
    @patch('readthedocs.builds.models.Version.get_conf_py_path')
    @patch('readthedocs.projects.models.Project.checkout_path')
    def test_multiple_conf_py(
            self, checkout_path, get_conf_py_path, _, get_config_params,
            create_index, docs_dir):
        """
        Test for a project with multiple ``conf.py`` files.

        An error should be raised to the user if we can't
        guess the correct conf.py file.
        """

        tmp_docs_dir = py.path.local(tempfile.mkdtemp())
        tmp_docs_dir.join('conf.py').write('')
        tmp_docs_dir.join('test').mkdir().join('conf.py').write('')
        docs_dir.return_value = str(tmp_docs_dir)
        checkout_path.return_value = str(tmp_docs_dir)
        create_index.return_value = 'README.rst'
        get_config_params.return_value = {}
        get_conf_py_path.side_effect = ProjectConfigurationError
        python_env = Virtualenv(
            version=self.version,
            build_env=self.build_env,
            config=None,
        )
        base_sphinx = BaseSphinx(
            build_env=self.build_env,
            python_env=python_env,
        )
        with pytest.raises(ProjectConfigurationError):
            base_sphinx.append_conf()


@override_settings(PRODUCTION_DOMAIN='readthedocs.org')
class MkdocsBuilderTest(TestCase):

    def setUp(self):
        self.project = get(Project, documentation_type='mkdocs', name='mkdocs')
        self.version = get(Version, project=self.project)

        self.build_env = namedtuple('project', 'version')
        self.build_env.project = self.project
        self.build_env.version = self.version

    @patch('readthedocs.doc_builder.base.BaseBuilder.run')
    @patch('readthedocs.projects.models.Project.checkout_path')
    def test_append_conf_create_yaml(self, checkout_path, run):
        tmpdir = tempfile.mkdtemp()
        os.mkdir(os.path.join(tmpdir, 'docs'))
        checkout_path.return_value = tmpdir

        python_env = Virtualenv(
            version=self.version,
            build_env=self.build_env,
            config=None,
        )
        self.searchbuilder = MkdocsHTML(
            build_env=self.build_env,
            python_env=python_env,
        )
        self.searchbuilder.append_conf()

        run.assert_called_with('cat', 'mkdocs.yml', cwd=mock.ANY)

        # There is a mkdocs.yml file created
        generated_yaml = os.path.join(tmpdir, 'mkdocs.yml')
        self.assertTrue(os.path.exists(generated_yaml))
        config = yaml.safe_load(open(generated_yaml))
        self.assertEqual(
            config['docs_dir'],
            os.path.join(tmpdir, 'docs')
        )
        self.assertEqual(
            config['extra_css'],
            [
                'http://readthedocs.org/static/css/badge_only.css',
                'http://readthedocs.org/static/css/readthedocs-doc-embed.css'
            ]
        )
        self.assertEqual(
            config['extra_javascript'],
            [
                'readthedocs-data.js',
                'http://readthedocs.org/static/core/js/readthedocs-doc-embed.js',
                'http://readthedocs.org/static/javascript/readthedocs-analytics.js',
            ]
        )
        self.assertIsNone(
            config['google_analytics'],
        )
        self.assertEqual(
            config['site_name'],
            'mkdocs'
        )

    @patch('readthedocs.doc_builder.base.BaseBuilder.run')
    @patch('readthedocs.projects.models.Project.checkout_path')
    def test_append_conf_existing_yaml_on_root(self, checkout_path, run):
        tmpdir = tempfile.mkdtemp()
        os.mkdir(os.path.join(tmpdir, 'docs'))
        yaml_file = os.path.join(tmpdir, 'mkdocs.yml')
        yaml.safe_dump(
            {
                'site_name': 'mkdocs',
                'google_analytics': ['UA-1234-5', 'mkdocs.org'],
                'docs_dir': 'docs',
            },
            open(yaml_file, 'w')
        )
        checkout_path.return_value = tmpdir

        python_env = Virtualenv(
            version=self.version,
            build_env=self.build_env,
            config=None,
        )
        self.searchbuilder = MkdocsHTML(
            build_env=self.build_env,
            python_env=python_env,
        )
        self.searchbuilder.append_conf()

        run.assert_called_with('cat', 'mkdocs.yml', cwd=mock.ANY)

        config = yaml.safe_load(open(yaml_file))
        self.assertEqual(
            config['docs_dir'],
            'docs'
        )
        self.assertEqual(
            config['extra_css'],
            [
                'http://readthedocs.org/static/css/badge_only.css',
                'http://readthedocs.org/static/css/readthedocs-doc-embed.css'
            ]
        )
        self.assertEqual(
            config['extra_javascript'],
            [
                'readthedocs-data.js',
                'http://readthedocs.org/static/core/js/readthedocs-doc-embed.js',
                'http://readthedocs.org/static/javascript/readthedocs-analytics.js',
            ]
        )
        self.assertIsNone(
            config['google_analytics'],
        )
        self.assertEqual(
            config['site_name'],
            'mkdocs'
        )

    @patch('readthedocs.doc_builder.base.BaseBuilder.run')
    @patch('readthedocs.projects.models.Project.checkout_path')
    def test_override_theme_new_style(self, checkout_path, run):
        tmpdir = tempfile.mkdtemp()
        os.mkdir(os.path.join(tmpdir, 'docs'))
        yaml_file = os.path.join(tmpdir, 'mkdocs.yml')
        yaml.safe_dump(
            {
                'theme': {
                    'name': 'readthedocs',
                },
                'site_name': 'mkdocs',
                'docs_dir': 'docs',
            },
            open(yaml_file, 'w')
        )
        checkout_path.return_value = tmpdir

        python_env = Virtualenv(
            version=self.version,
            build_env=self.build_env,
            config=None,
        )
        self.searchbuilder = MkdocsHTML(
            build_env=self.build_env,
            python_env=python_env,
        )
        self.searchbuilder.append_conf()

        run.assert_called_with('cat', 'mkdocs.yml', cwd=mock.ANY)

        config = yaml.safe_load(open(yaml_file))
        self.assertEqual(
            config['theme'],
            {
                'name': 'readthedocs',
                'custom_dir': BaseMkdocs.READTHEDOCS_TEMPLATE_OVERRIDE_DIR
            }
        )

    @patch('readthedocs.doc_builder.base.BaseBuilder.run')
    @patch('readthedocs.projects.models.Project.checkout_path')
    def test_override_theme_old_style(self, checkout_path, run):
        tmpdir = tempfile.mkdtemp()
        os.mkdir(os.path.join(tmpdir, 'docs'))
        yaml_file = os.path.join(tmpdir, 'mkdocs.yml')
        yaml.safe_dump(
            {
                'theme': 'readthedocs',
                'site_name': 'mkdocs',
                'docs_dir': 'docs',
            },
            open(yaml_file, 'w')
        )
        checkout_path.return_value = tmpdir

        python_env = Virtualenv(
            version=self.version,
            build_env=self.build_env,
            config=None,
        )
        self.searchbuilder = MkdocsHTML(
            build_env=self.build_env,
            python_env=python_env,
        )
        self.searchbuilder.append_conf()

        run.assert_called_with('cat', 'mkdocs.yml', cwd=mock.ANY)

        config = yaml.safe_load(open(yaml_file))
        self.assertEqual(
            config['theme_dir'],
            BaseMkdocs.READTHEDOCS_TEMPLATE_OVERRIDE_DIR
        )

    @patch('readthedocs.doc_builder.base.BaseBuilder.run')
    @patch('readthedocs.projects.models.Project.checkout_path')
    def test_dont_override_theme(self, checkout_path, run):
        tmpdir = tempfile.mkdtemp()
        os.mkdir(os.path.join(tmpdir, 'docs'))
        yaml_file = os.path.join(tmpdir, 'mkdocs.yml')
        yaml.safe_dump(
            {
                'theme': 'not-readthedocs',
                'theme_dir': 'not-readthedocs',
                'site_name': 'mkdocs',
                'docs_dir': 'docs',
            },
            open(yaml_file, 'w')
        )
        checkout_path.return_value = tmpdir

        python_env = Virtualenv(
            version=self.version,
            build_env=self.build_env,
            config=None,
        )
        self.searchbuilder = MkdocsHTML(
            build_env=self.build_env,
            python_env=python_env,
        )
        self.searchbuilder.append_conf()

        run.assert_called_with('cat', 'mkdocs.yml', cwd=mock.ANY)

        config = yaml.safe_load(open(yaml_file))
        self.assertEqual(
            config['theme_dir'],
            'not-readthedocs'
        )
