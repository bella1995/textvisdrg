"""
Define common admin and maintenance tasks here.
For more info: http://docs.fabfile.org/en/latest/
"""

django_project_name = 'msgvis'
pip_requirements = {
    'dev': ('-r requirements/dev.txt',),
    'prod': ('-r requirements/prod.txt',),
    'test': ('-r requirements/test.txt',),
}

test_data_apps = ('base', 'api', 'corpus',
                  'dimensions', 'datatable',
                  'importer', 'enhance', 'questions',
                  'auth',)

# Model keys to fixture paths from PROJECT_ROOT
model_fixtures = {
    'corpus.Language': 'msgvis/apps/corpus/fixtures/languages.json',
    'corpus.MessageType': 'msgvis/apps/corpus/fixtures/messagetypes.json',
    'corpus.Sentiment': 'msgvis/apps/corpus/fixtures/sentiments.json',
    'corpus.Timezone': 'msgvis/apps/corpus/fixtures/timezones.json',
}

import sys
import os
from path import path
from fabric.api import local, run, env, prefix, quiet, lcd
from fabric.colors import red, green, yellow
from fabric.operations import prompt

PROJECT_ROOT = path(__file__).abspath().realpath().dirname()
sys.path.append(PROJECT_ROOT / 'setup')
from fabutils import utils as fabutils

fabutils.configure(PROJECT_ROOT, django_project_name)


def dependencies(environment='dev'):
    """Installs Python, NPM, and Bower packages"""

    print green("Updating %s dependencies..." % environment)

    reqs = pip_requirements[environment]
    if fabutils.pip_install(reqs) and \
        fabutils.npm_install() and \
        fabutils.bower_install():
        print "Dependency update successful."


def migrate():
    """Runs migrations"""

    print green("Running migrations...")
    if fabutils.manage_py('migrate'):
        print "Migrations successful."


def build_static():
    """Builds static files for production"""

    print green("Gathering and preprocessing static files...")
    fabutils.manage_py('collectstatic --noinput')
    fabutils.manage_py('compress')


def docs(easy=None):
    """Build the documentation"""

    print green("Rebuilding the Sphinx documentation...")
    with lcd(PROJECT_ROOT / 'docs'):
        if easy is not None:
            local('make clean html')
        else:
            local('make clean html SPHINXOPTS="-n -W -T"')


def manage(command):
    """Run a Django management command."""
    fabutils.manage_py(command)


def test(settings_module='msgvis.settings.test'):
    """Run tests"""
    fabutils.django_tests(settings_module, coverage=False)


def test_coverage(settings_module='msgvis.settings.test'):
    """Run tests with coverage"""
    fabutils.django_tests(settings_module, coverage=True)


def runserver():
    """Runs the Django development server"""

    print green("Running the development webserver...")
    denv = fabutils.dot_env()
    host = denv.get('SERVER_HOST', '0.0.0.0')
    port = denv.get('PORT', '8000')
    fabutils.manage_py('runserver %s:%s' % (host, port))


def load_test_data():
    """Load test data from test_data.json"""

    infile = PROJECT_ROOT / 'setup' / 'fixtures' / 'test_data.json'

    if infile.exists():
        print green("Loading test data from %s" % infile)
        if fabutils.manage_py("loaddata %s" % infile):
            print "Load test data successful."
    else:
        print yellow("No test data found")


def make_test_data():
    """Updates the test_data.json file based on what is in the database"""

    outfile = PROJECT_ROOT / 'setup' / 'fixtures' / 'test_data.json'

    print green("Saving test data from %s to %s" % (test_data_apps, outfile))
    args = ' '.join(test_data_apps + ('--exclude=auth.Permission',))
    if fabutils.manage_py("dumpdata --indent=2 %s > %s" % (args, outfile)):
        print "Make test data successful."


def generate_fixtures(app_or_model=None):
    """
    Regenerate configured fixtures from the database.

    A Django app name or app model (app.Model) may be given as a parameter.
    """
    model_filter = None
    app_filter = None
    if app_or_model:
        if '.' in app_or_model:
            model_filter = app_or_model
        else:
            app_filter = '%s.' % app_or_model

    generated = []
    for model, fixturefile in model_fixtures.iteritems():
        if model_filter and model != model_filter:
            continue
        if app_filter and not model.startswith(app_filter):
            continue

        fabutils.manage_py('dumpdata --indent=2 {model} > {out}'.format(
            model=model,
            out=PROJECT_ROOT / fixturefile,
        ))
        generated.append(fixturefile)

    print "Generated %d fixtures:" % len(generated)
    if len(generated) > 0:
        print " - " + '\n - '.join(generated)


def load_fixtures(app_or_model=None):
    """
    Replaces the database tables with the contents of fixtures.

    A Django app name or app model (app.Model) may be given as a parameter.
    """

    model_filter = None
    app_filter = None
    if app_or_model:
        if '.' in app_or_model:
            model_filter = app_or_model
        else:
            app_filter = '%s.' % app_or_model

    for model, fixturefile in model_fixtures.iteritems():
        if model_filter and model != model_filter:
            continue
        if app_filter and not model.startswith(app_filter):
            continue
        fabutils.manage_py('syncdata %s' % (PROJECT_ROOT / fixturefile,))



def reset_db():
    """Removes all of the tables"""
    fabutils.manage_py("reset_db")


def clear_cache():
    """Deletes the cached static files"""

    settings = fabutils.django_settings()

    if hasattr(settings, 'COMPRESS_ROOT'):
        cache_dir = settings.COMPRESS_ROOT / settings.COMPRESS_OUTPUT_DIR

        # a safety check
        if cache_dir.exists() and cache_dir.endswith("CACHE"):
            print green("Removing %s" % cache_dir)
            cache_dir.rmdir_p()
            print "Clear cache successful."
    else:
        print yellow("Django not configured for static file compression")


def pull():
    """Just runs git pull"""

    print green("Pulling latest code...")
    local('git pull')
    print "Git pull successful."


def reset_dev(pull=None):
    """
    Fully update the development environment.
    This is useful after a major update.

    Runs reset_db, [git pulls], installs dependencies, migrate, load_test_data, and clear_cache.
    """
    print "\n"
    reset_db()

    if pull is not None:
        print "\n"
        pull()

    print "\n"
    dependencies()

    print "\n"
    migrate()

    print "\n"
    load_test_data()

    print "\n"
    clear_cache()


def make_test_env(outpath=None):
    if outpath is None:
        outpath = PROJECT_ROOT / '.env'
    else:
        outpath = path(outpath)

    # An empty file for now
    local('touch %s' % outpath)


def interpolate_env(outpath=None):
    """Writes a .env file with variables interpolated from the current environment"""

    if outpath is None:
        outpath = PROJECT_ROOT / '.env'
    else:
        outpath = path(outpath)

    dot_env_path = PROJECT_ROOT / 'setup' / 'templates' / 'dot_env'

    fabutils.django_render(dot_env_path, outpath, os.environ)


def restart_webserver():
    """Restart a local gunicorn process"""
    print green("Restarting gunicorn...")
    fabutils.manage_py('supervisor restart webserver')


def supervisor():
    """Starts the supervisor process"""
    print green("Supervisor launching...")
    fabutils.manage_py('supervisor')


def check_database():
    """Makes sure the database is accessible"""

    if fabutils.test_database():
        print green("Database is available")
    else:
        settings = fabutils.django_settings()
        print red("Database is not available! (%s)" % settings.DATABASES['default']['NAME'])


def print_env():
    """Print the local .env file contents"""
    denv = fabutils.dot_env()
    import pprint

    pprint.pprint(denv)


def deploy():
    """
    SSH into a remote server, run commands to update deployment,
    and start the server.
    
    This requires that the server is already running a 
    fairly recent copy of the code.

    Furthermore, the app must use a
    """

    denv = fabutils.dot_env()

    host = denv.get('DEPLOY_HOST', None)
    virtualenv = denv.get('DEPLOY_VIRTUALENV', None)

    if host is None:
        print red("No DEPLOY_HOST in .env file")
        return
    if virtualenv is None:
        print red("No DEPLOY_VIRTUALENV in .env file")
        return

    env.host_string = host

    with prefix('workon %s' % virtualenv):

        # Check prereqs
        with quiet():
            pips = run('pip freeze')
            if "Fabric" not in pips or 'path.py' not in pips:
                print green("Installing Fabric...")
                run('pip install Fabric path.py')

        run('fab pull')
        run('fab dependencies:prod')
        run('fab print_env check_database migrate')
        run('fab build_static restart_webserver')

