#!/usr/bin/python3
# vim: ts=4 sw=4 noet

# python3-venv
# python3-systemd

# Built-in packages
import datetime
import logging
import os
import sys

# Third-party libraries
import docker
from docker.errors import DockerException


# Set up logging

# Start with basic logging configuration to stderr
logging.basicConfig(
	stream=sys.stderr,
	level=(
		logging.INFO
		if 'LOG_LEVEL' not in os.environ
		else os.environ['LOG_LEVEL']
	),
)

# Make the logger we're going to use, with some convenience functions.
logger = logging.getLogger(__name__)
exception = logging.exception
error = logger.error
warn = logger.warning
info = logger.info
debug = logger.debug

# If we are running under Systemd v232+, log to the journal instead of stderr.
logging_configured = False
if 'INVOCATION_ID' in os.environ:
	info('Trying to switch logging to journald')
	try:
		import systemd
		logging.basicConfig(
			force=True,
			handlers=[
				systemd.journal.JournalHandler(
					SYSLOG_IDENTIFIER='image_cleanup',
				),
			],
			level=(
				logging.INFO
				if 'LOG_LEVEL' not in os.environ
				else os.environ['LOG_LEVEL']
			),
		)
	except ImportError:
		# It's OK if we don't have the systemd package, we'll just stick to
		# normal logging.
		warn('Unable to load the systemd Python module.  Falling back to stderr logging.')
		pass


# Time to do some actual work!

# Connect to Docker
try:
	client = docker.from_env()
except DockerException:
	exception('Unable to connect to the Docker daemon')
	sys.exit(1)

# Iterate through container images, looking for ones that are not tagged.
for image in client.images.list():
	# Grab some common attributes
	image_id = image.short_id
	image_tags = image.tags
	image_date = datetime.datetime.fromisoformat(image.attrs['Created'])
	
	# Does the image have tags?  If yes, keep the image
	if len(image_tags) > 0:
		debug(f"Skipping image {image_id}, tagged to {image_tags}")
		continue

	# We're about to remove a container image.

	# Grab some attributes that might not exist
	image_source = (
		image.labels['org.opencontainers.image.source']
		if 'org.opencontainers.image.source' in image.labels
		else 'unknown'
	)
	image_revision = (
		image.labels['org.opencontainers.image.revision']
		if 'org.opencontainers.image.revision' in image.labels
		else 'unknown'
	)
	image_version = (
		image.labels['org.opencontainers.image.version']
		if 'org.opencontainers.image.version' in image.labels
		else 'unknown'
	)

	# Log removal of the image
	info(f"Removing image {image_id}, source {image_source} version {image_version} revision {image_revision}")

	# Remove the image
	try:
		remove_result = image.remove()
	except DockerException:
		exception(f"Unable to remove image {image_id}")

	# If we wanted, the result contains an array of string-string dicts.
	# One dict will have the key 'Untagged', confirming which image was
	# deleted.
	# The other dicts will have the key 'Deleted', and give the ID of layers
	# that have been deleted.

info('Cleanup complete!')
sys.exit(0)
