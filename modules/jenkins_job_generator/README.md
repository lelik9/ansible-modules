
jenkins\_job\_generator - Wrapper around jenkins job builder
=======================================================================================================================================================

Synopsis
-----------------------------------------------------------

-   “This is a wrapper around jenkins job builder which provide
    idempotency state of jobs inside jenkins JJB documentation -
    [https://docs.openstack.org/infra/jenkins-job-builder/](https://docs.openstack.org/infra/jenkins-job-builder/)”

Requirements (on host that executes module
-------------------------------------------------------------------------------------------------------------------------------

jenkins-job-builder. You could install it via pip install jenkins-job-builder

Options
---------------------------------------------------------

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
    files:
        description:
            - List of files with jenkins job config. File should be in YAML format.
        required: true
    path:
        description:
            - Path to job configuration files
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

Examples
-----------------------------------------------------------

    # Copy job configuration from template
    - name: Create job tamplate
      template:
        src: jobs/production.yaml.j2
        dest: /tmp/production.yaml

    # Update or create jobs
    - name: Generate jobs
      jenkins_job_generator:
        files:
          - production.yaml
        path: /tmp
        action: update
        user: jenkins
        password: jenkins

Return Values
---------------------------------------------------------------------

Common return values are documented
[here](../common_return_values.html#common-return-values), the following
are the fields unique to this {{plugin\_type}}:

  name                description                                           returned   type   sample
  ------------------- ----------------------------------------------------- ---------- ------ --------
  message             The output message that the sample module generates                     
  original\_message   The output message that the sample module generates              str    

### Author

> -   Aleksei Philippov