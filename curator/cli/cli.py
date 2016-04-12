import elasticsearch
import click
import re
from .utils import *
from .. import __version__

import logging
logger = logging.getLogger(__name__)

try:
    from logging import NullHandler
except ImportError:
    from logging import Handler

    class NullHandler(Handler):
        def emit(self, record):
            pass

DEFAULT_ARGS = {
    'host': 'localhost',
    'url_prefix': '',
    'port': 9200,
    'http_auth': None,
    'use_ssl': False,
    'timeout': 30,
    'dry_run': False,
    'debug': False,
    'log_level': 'INFO',
    'logformat': 'default',
}

@click.group()
@click.option('--host', help='Elasticsearch host.', default=DEFAULT_ARGS['host'])
@click.option('--url_prefix', help='Elasticsearch http url prefix.', default=DEFAULT_ARGS['url_prefix'])
@click.option('--port', help='Elasticsearch port.', default=DEFAULT_ARGS['port'], type=int)
@click.option('--use_ssl', help='Connect to Elasticsearch through SSL.', is_flag=True, default=DEFAULT_ARGS['use_ssl'])
@click.option('--certificate', help='Path to certificate to use for SSL validation. (OPTIONAL)', type=str, default=None)
@click.option('--client-cert', help='Path to file containing SSL certificate for client auth. (OPTIONAL)', type=str, default=None)
@click.option('--client-key', help='Path to file containing SSL key for client auth. (OPTIONAL)', type=str, default=None)
@click.option('--ssl-no-validate', help='Do not validate SSL certificate', is_flag=True)
@click.option('--http_auth', help='Use Basic Authentication ex: user:pass', default=DEFAULT_ARGS['http_auth'])
@click.option('--access-key', help='Access key of the IAM user to connect to the AWS Elasticsearch Service host. (OPTIONAL)', default=None)
@click.option('--secret-access-key', help='Secret Access key of the IAM user, (OPTIONAL)', default=None)
@click.option('--region', help='AWS region of the Elasticsearch Service host. (OPTIONAL)', default=None)
@click.option('--timeout', help='Connection timeout in seconds.', default=DEFAULT_ARGS['timeout'], type=int)
@click.option('--master-only', is_flag=True, help='Only operate on elected master node.')
@click.option('--dry-run', is_flag=True, help='Do not perform any changes.', default=DEFAULT_ARGS['dry_run'])
@click.option('--debug', is_flag=True, help='Debug mode', default=DEFAULT_ARGS['debug'])
@click.option('--loglevel', help='Log level', default=DEFAULT_ARGS['log_level'])
@click.option('--logfile', help='log file')
@click.option('--logformat', help='Log output format [default|logstash].', default=DEFAULT_ARGS['logformat'])
@click.option('--quiet', help='Suppress command-line output.', is_flag=True)
@click.version_option(version=__version__)
@click.pass_context
def cli(ctx, host, url_prefix, port, use_ssl, certificate, client_cert, client_key, ssl_no_validate, http_auth, access_key, secret_access_key, region, timeout, master_only, dry_run, debug, loglevel, logfile, logformat, quiet):
    """
    Curator for Elasticsearch indices.

    See http://elastic.co/guide/en/elasticsearch/client/curator/current
    """

    # Setup logging
    if debug:
        numeric_log_level = logging.DEBUG or loglevel.upper() == 'DEBUG'
        format_string = '%(asctime)s %(levelname)-9s %(name)22s %(funcName)22s:%(lineno)-4d %(message)s'
    else:
        numeric_log_level = getattr(logging, loglevel.upper(), None)
        format_string = '%(asctime)s %(levelname)-9s %(message)s'
        if not isinstance(numeric_log_level, int):
            raise ValueError('Invalid log level: {0}'.format(loglevel))

    handler = logging.StreamHandler(
        open(logfile, 'a') if logfile else sys.stdout)
    if logformat == 'logstash':
        ctx.params['quiet'] = True
        handler.setFormatter(LogstashFormatter())
    else:
        handler.setFormatter(logging.Formatter(format_string))
    logging.root.addHandler(handler)
    logging.root.setLevel(numeric_log_level)
    logger = logging.getLogger('curator.cli')

    # Test whether certificate is a valid file path
    if use_ssl is True and certificate is not None:
        try:
            open(certificate, 'r')
        except IOError:
            logger.error('Could not open certificate at {0}'.format(certificate))
            msgout('Error: Could not open certificate at {0}'.format(certificate), error=True, quiet=quiet)
            sys.exit(1)

    # Test whether client_cert is a valid file path
    if use_ssl is True and client_cert is not None:
        try:
            open(client_cert, 'r')
        except IOError:
            logger.error('Could not open client cert at {0}'.format(client_cert))
            msgout('Error: Could not open client cert at {0}'.format(client_cert), error=True, quiet=quiet)
            sys.exit(1)

    # Test whether client_key is a valid file path
    if use_ssl is True and client_key is not None:
        try:
            open(client_key, 'r')
        except IOError:
            logger.error('Could not open client key at {0}'.format(client_key))
            msgout('Error: Could not open client key at {0}'.format(client_key), error=True, quiet=quiet)
            sys.exit(1)

    # Filter out logging from Elasticsearch and associated modules by default
    if not debug:
        for handler in logging.root.handlers:
            handler.addFilter(
                Whitelist(
                    'root', '__main__', 'curator', 'curator.curator',
                    'curator.api', 'curator.cli', 'curator.api',
                    'curator.cli'
                )
            )

    # Setting up NullHandler to handle nested elasticsearch.trace Logger
    # instance in elasticsearch python client
    logging.getLogger('elasticsearch.trace').addHandler(NullHandler())
