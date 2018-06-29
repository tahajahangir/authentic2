@Library('eo-jenkins-lib@wip/publish_coverage_native') import eo.Utils

pipeline {
    agent any
    stages {
        stage('Unit Tests') {
            steps {
                sh './jenkins.sh'
            }
        }
        stage('Packaging') {
            steps {
                script {
                    if (env.JOB_NAME == 'authentic2' && env.GIT_BRANCH == 'origin/master') {
                        sh 'sudo -H -u eobuilder /usr/local/bin/eobuilder -d jessie authentic'
                    }
                }
            }
        }
    }
    post {
        always {
            script {
                utils = new Utils()
                utils.mail_notify(currentBuild, env, 'admin+jenkins-authentic@entrouvert.com')
                utils.publish_coverage('coverage-*.xml')
                utils.publish_coverage_native(
                    'index.html', 'htmlcov-coverage-dj18-authentic-pg', 'Coverage a2')
                utils.publish_coverage_native(
                    'index.html', 'htmlcov-coverage-dj18-rbac-pg', , 'Coverage rbac')
                utils.publish_pylint('pylint.out')
            }
            junit 'junit-*.xml'
        }
        success {
            cleanWs()
        }
    }
}
