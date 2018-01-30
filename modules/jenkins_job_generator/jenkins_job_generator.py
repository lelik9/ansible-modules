#!/usr/bin/python
# Copyright (c) 2017 Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
import json
import logging
import sys
import time
import traceback

from ansible.module_utils.basic import AnsibleModule
import xml.etree.ElementTree as ET

# Import Jenkins builder
try:
    from jenkins_jobs.builder import JenkinsManager
    from jenkins_jobs.cli.entry import JenkinsJobs
    from jenkins_jobs.cli.subcommand.update import UpdateSubCommand
    from jenkins_jobs.parser import YamlParser
    from jenkins_jobs.registry import ModuleRegistry
    from jenkins_jobs.xml_config import XmlJobGenerator
    from jenkins_jobs.xml_config import XmlViewGenerator
    from jenkins_jobs.errors import JenkinsJobsException
except ImportError as e:
    print(json.dumps(
        {
            'original_message': str(e),
            'message': 'Jenkins Job Builder not found in system. Please install it: pip install jenkins-job-builder'
        }
    ))
    sys.exit(1)

logging.basicConfig(filename="jenkins_job.log", level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger()

ANSIBLE_METADATA = {
    'metadata_version': '1.1',
    'status': ['preview'],
    'supported_by': 'community'
}

DOCUMENTATION = '''
---
module: jenkins_job_generator

short_description: Wrapper around jenkins job builder

version_added: "0.1"

description:
    - "This is a wrapper around jenkins job builder which provide idempotency state of jobs inside jenkins
    JJB documentation - https://docs.openstack.org/infra/jenkins-job-builder/"

options:
    jenkins_server:
        description:
            - Jenkins server address. Default is http://127.0.0.1:8080
        required: false
        default: http://127.0.0.1:8080
    user:
        description:
            - Username to access jenkins server API
        required: false
        default: ''
    password:
        description:
            - User password
        required: false
        default: ''
    jobs:
        description:
            - List of jobs which you want to update or delete. Note: Path variable should be set
        required: true
    path:
        description:
            - Path to job configuration files
        required: true
    file:
        description:
            - File name wth job configuration. You shouldn't set path and job with this var
        required: true
    workers:
        description:
            - Number of workers
        required: false
        default: 1
    delete_old:
        description:
            - Delete old jobs
        required: false
        default: false
    action:
        description:
            - Which action execute (update or delete)
        required: true
        default: update
        choices:
           - update
           - delete

requirements: jenkins-job-builder

author:
    - Aleksei Philippov
'''

EXAMPLES = '''
# Copy job configuration from template
- name: Create job tamplate
  template:
    src: jobs/production.yaml.j2
    dest: /tmp/production.yaml

# Update or create all jobs from file
- name: Generate jobs
  jenkins_job_generator:
    file:
      - /tmp/production.yaml
    action: update
    user: jenkins
    password: jenkins

# Update or create all jobs in the path
- name: Generate jobs
  jenkins_job_generator:
    path: /tmp
    action: update
    user: jenkins
    password: jenkins

# Update or create selected jobs in the path
- name: Generate jobs
  jenkins_job_generator:
    path: /tmp
    jobs:
      - build
      - test
    action: update
    user: jenkins
    password: jenkins
'''

RETURN = '''
original_message:
    description: The output message that the sample module generates
    type: str
message:
    description: The output message that the sample module generates
'''


class JobBuilder(JenkinsManager):
    def changed(self, job):

        changed = self._is_jenkins_job_changed(job=job)

        if not changed:
            logger.debug("'{0}' has not changed".format(job.name))
        else:
            logger.debug("'{0}' has changed".format(job.name))
        return changed

    def _is_jenkins_job_changed(self, job):
        job_config = self.jenkins.get_job_config(job.name)
        current_job_config = job.output()

        xml1 = ET.fromstring(job_config)
        xml2 = ET.fromstring(current_job_config)

        return not self.xml_compare(xml1, xml2)

    def xml_compare(self, x1, x2):
        """
        Compares two xml etrees
        :param x1: the first tree
        :param x2: the second tree
        :return:
            True if both files match
        """

        if x1.tag != x2.tag:
            return False
        for name, value in x1.attrib.items():
            if x2.attrib.get(name) != value:
                return False
        for name in x2.attrib.keys():
            if name not in x1.attrib:
                return False
        if not self.text_compare(x1.text, x2.text):
            return False
        if not self.text_compare(x1.tail, x2.tail):
            return False
        cl1 = x1.getchildren()
        cl2 = x2.getchildren()
        if len(cl1) != len(cl2):
            return False
        i = 0
        for c1, c2 in zip(cl1, cl2):
            i += 1
            if not self.xml_compare(c1, c2):
                return False
        return True

    @staticmethod
    def text_compare(t1, t2):
        """
        Compare two text strings
        :param t1: text one
        :param t2: text two
        :return:
            True if a match
        """
        if not t1 and not t2:
            return True
        if t1 == '*' or t2 == '*':
            return True
        return (t1 or '').strip() == (t2 or '').strip()


class Executor(UpdateSubCommand):
    def _generate_xmljobs(self, options, jjb_config=None):
        builder = JobBuilder(jjb_config)

        logger.info("Updating jobs in {0} ({1})".format(
            options.path, options.names))
        orig = time.time()

        # Generate XML
        parser = YamlParser(jjb_config)
        registry = ModuleRegistry(jjb_config, builder.plugins_list)
        xml_job_generator = XmlJobGenerator(registry)
        xml_view_generator = XmlViewGenerator(registry)

        parser.load_files(options.path)
        registry.set_parser_data(parser.data)

        job_data_list, view_data_list = parser.expandYaml(
            registry, options.names)

        xml_jobs = xml_job_generator.generateXML(job_data_list)
        xml_views = xml_view_generator.generateXML(view_data_list)

        jobs = parser.jobs
        step = time.time()
        logging.debug('%d XML files generated in %ss',
                      len(jobs), str(step - orig))

        return builder, xml_jobs, xml_views

    def execute(self, options, jjb_config):
        if options.n_workers < 0:
            raise JenkinsJobsException(
                'Number of workers must be equal or greater than 0')

        builder, xml_jobs, xml_views = self._generate_xmljobs(
            options, jjb_config)

        if len(xml_jobs) == 0 and len(xml_views) == 0:
            raise Exception('No jobs or view found')

        jobs, num_updated_jobs = builder.update_jobs(
            xml_jobs, n_workers=options.n_workers)
        logger.info("Number of jobs updated: %d", num_updated_jobs)

        views, num_updated_views = builder.update_views(
            xml_views, n_workers=options.n_workers)
        logger.info("Number of views updated: %d", num_updated_views)

        keep_jobs = [job.name for job in xml_jobs]
        if options.delete_old:
            n = builder.delete_old_managed(keep=keep_jobs)
            logger.info("Number of jobs deleted: %d", n)

        return num_updated_jobs, num_updated_views


class ActionRunner(object):
    LOG_LEVEL = 'debug'

    def __init__(self, jenkins_server, user, password, result, **kwargs):
        self.result = result

        self.executor = Executor()

        self.jenkins_server = jenkins_server
        self.options = [
            '--user', user,
            '--password', password,
            '--log_level', self.LOG_LEVEL
        ]

    def update(self, delete_old, workers, path=None, file=None, jobs=None, **kwargs):
        action_options = [
            'update',
            '--workers', str(workers),
        ]

        if delete_old:
            action_options.insert(1, '--delete_old')

        if path is not None and jobs is not None:
            action_options.append(path)
            action_options.extend(jobs)
        elif path is not None:
            action_options.append(path)
        elif file is not None:
            action_options.append(file)
        else:
            raise Exception('Incorrect options. File or path with job files should be provided')

        self.options.extend(action_options)

        jjb_configs = JenkinsJobs(self.options)
        jjb_configs.jjb_config.jenkins['url'] = self.jenkins_server

        num_updated_jobs, num_updated_views = \
            self.executor.execute(options=jjb_configs.options, jjb_config=jjb_configs.jjb_config)

        if num_updated_jobs == 0 & num_updated_views == 0:
            self.result['original_message'] = 'Nothing changed'
            self.result['message'] = 'goodbye'
        else:
            self.result['changed'] = True
            self.result['original_message'] = 'Changed jobs: {}. Changed views: {}.'.format(num_updated_jobs,
                                                                                            num_updated_views)
            self.result['message'] = 'goodbye'
        return self.result

    def delete(self, **kwargs):
        raise Exception('This actions currently unavailable!')


def run_module():
    module_args = dict(
        jenkins_server=dict(type='str', required=False, default='http://127.0.0.1:8080'),
        user=dict(type='str', required=False, default=''),
        password=dict(type='str', required=False, default='', no_log=True),
        jobs=dict(type='list', required=False),
        path=dict(type='str', required=False),
        file=dict(type='str', required=False),
        workers=dict(type='int', required=False, default=1),
        delete_old=dict(type='bool', required=False, default=False),
        action=dict(choices=[
            'update',
            'delete'
        ],
            default='update'),
    )

    result = dict(
        changed=False,
        original_message='',
        message=''
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    if module.check_mode:
        return result

    try:
        action = ActionRunner(result=result, **module.params)

        result = action.__getattribute__(module.params['action'])(**module.params)

    except Exception as e:
        result['message'] = traceback.format_exc()
        module.fail_json(msg=str(e), **result)

    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
