// CI/CD-Pipeline der Pseudonymisierung
//
// Vier getrennte Single-Branch-Jobs (dev/test/int/prod) verwenden DASSELBE
// Jenkinsfile. Die Umgebung wird aus dem ausgecheckten Zweig abgeleitet -
// nicht aus dem Jobnamen und nicht ueber when{branch}, denn ohne Multibranch
// ist BRANCH_NAME nicht gesetzt.
//
// Voraussetzungen Jenkins:
//   - SSH-Credential 'hermespia-deploy' (u7031y_kaspar@83.228.238.194)
//   - Docker + Docker-Pipeline-Plugin (nur fuer den Testcontainer)
//
// Voraussetzungen Host (einmalig, siehe docs/INSTALLATION.md):
//   - .env je Stufe mit PSEUDO_TRESOR_SCHLUESSEL
//   - registrierte Anwendung + hinterlegter Anbieterschluessel
//
// Der Dienst bekommt KEINE Site und KEINEN PHP-Proxy: er bindet auf
// 127.0.0.1. Deshalb gibt es hier keinen Docroot-Schritt.

pipeline {
    agent any

    options {
        timestamps()
        // Wichtig: zwei gleichzeitige Deploys derselben Stufe erzeugen sonst
        // ein Wettrennen um den Port (Errno 98).
        disableConcurrentBuilds()
        timeout(time: 20, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }

    environment {
        DEPLOY_HOST = 'u7031y_kaspar@83.228.238.194'
        // Getestet wird auf der Python-Version des Zielhosts (3.9.2), NICHT auf
        // einer neueren. Sonst faellt eine Unvertraeglichkeit erst beim Deploy
        // auf - und genau daran waere presidio-analyzer gescheitert.
        TEST_IMAGE  = 'python:3.9-slim'
    }

    stages {

        stage('Umgebung bestimmen') {
            steps {
                script {
                    def roh = (env.GIT_BRANCH ?: env.BRANCH_NAME ?: '').trim()
                    def zweig = roh.replaceFirst(/^origin\//, '')
                                   .replaceFirst(/^refs\/heads\//, '')
                    def abbildung = [
                        'develop'    : 'develop',
                        'test'       : 'test',
                        'integration': 'integration',
                        'main'       : 'main',
                    ]
                    env.PSEUDO_UMGEBUNG = abbildung[zweig] ?: ''
                    if (!env.PSEUDO_UMGEBUNG) {
                        // Bewusst kein Rateverfahren: lieber nur testen als auf
                        // die falsche Stufe deployen.
                        echo "Zweig '${zweig}' ist keiner Stufe zugeordnet - es wird nur getestet."
                    } else {
                        echo "Zweig '${zweig}' -> Stufe '${env.PSEUDO_UMGEBUNG}'"
                    }
                    currentBuild.displayName = "#${env.BUILD_NUMBER} ${zweig}"
                }
            }
        }

        stage('Regressionstests') {
            steps {
                script {
                    docker.image(env.TEST_IMAGE).inside('-u root') {
                        sh '''
                            python --version
                            pip install --no-cache-dir -q -r requirements.txt
                            mkdir -p reports
                            # "python -m pytest", NICHT "pytest": nur diese Form
                            # legt das Arbeitsverzeichnis auf den Suchpfad, sonst
                            # scheitert "import app".
                            python -m pytest -q --junitxml=reports/junit.xml
                        '''
                    }
                }
            }
            post {
                always {
                    junit allowEmptyResults: false, testResults: 'reports/junit.xml'
                }
            }
        }

        stage('Deploy') {
            when { expression { return env.PSEUDO_UMGEBUNG?.trim() } }
            steps {
                sshagent(credentials: ['hermespia-deploy']) {
                    // Das Steuerskript wird ueber stdin gepipet statt inline
                    // zusammengebaut: eine Quelle der Wahrheit, und die
                    // Kommandozeile bleibt frei von Mustern, die sich selbst
                    // treffen koennten.
                    sh """
                        ssh -T -o StrictHostKeyChecking=no ${DEPLOY_HOST} \
                            bash -s deploy ${env.PSEUDO_UMGEBUNG} < deploy/pseudo_ctl.sh
                    """
                }
            }
        }

        stage('Rauchtest') {
            when { expression { return env.PSEUDO_UMGEBUNG?.trim() } }
            steps {
                sshagent(credentials: ['hermespia-deploy']) {
                    sh """
                        ssh -T -o StrictHostKeyChecking=no ${DEPLOY_HOST} \
                            bash -s health ${env.PSEUDO_UMGEBUNG} < deploy/pseudo_ctl.sh
                    """
                }
            }
        }

    }

    post {
        success {
            script {
                if (env.PSEUDO_UMGEBUNG?.trim()) {
                    echo "Gruen - Stufe ${env.PSEUDO_UMGEBUNG} laeuft und ist gesund."
                } else {
                    echo 'Gruen - Tests bestanden, kein Deploy (Zweig ohne Stufe).'
                }
            }
        }
        failure {
            echo 'Rot - Stage-Log und Testbericht pruefen. Bei Deploy-Fehlern zusaetzlich ' +
                 '~/logs/pseudo-watchdog.log und logs/error-<stufe>.log auf dem Host.'
        }
    }
}
