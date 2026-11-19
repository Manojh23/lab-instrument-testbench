pipeline {
    agent any
    options { timeout(time: 10, unit: 'MINUTES'); timestamps(); disableConcurrentBuilds() }
    stages {
        stage('Environment') {
            steps { sh 'python3 -m venv .venv && .venv/bin/pip install -e ".[test]"' }
        }
        stage('Verification and regression detection') {
            steps { sh '. .venv/bin/activate && bash scripts/check.sh' }
        }
    }
    post {
        always {
            junit testResults: 'reports/junit.xml', allowEmptyResults: false
            archiveArtifacts artifacts: 'reports/**', allowEmptyArchive: true
        }
    }
}
