from setuptools import setup

plugin_identifier = "octogoat"
plugin_package = "octoprint_octogoat"
plugin_name = "OctoGoat"
plugin_version = "0.1.0"
plugin_description = "Resumes, Realigns, Restores, Recovers, Failed prints easily, quickly and accurately  ."
plugin_author = "OctoGOAT"
plugin_author_email = "ksmith1489@protonmail.com"
plugin_url = ""
plugin_license = "AGPLv3"
plugin_requires = ["requests"]
additional_setup_parameters = {}

try:
    import octoprint_setuptools
except Exception:
    print("Could not import OctoPrint's setuptools, are you sure you are running that under the same python installation that OctoPrint is installed under?")
    import sys
    sys.exit(-1)

setup_parameters = octoprint_setuptools.create_plugin_setup_parameters(
    identifier=plugin_identifier,
    package=plugin_package,
    name=plugin_name,
    version=plugin_version,
    description=plugin_description,
    author=plugin_author,
    mail=plugin_author_email,
    url=plugin_url,
    license=plugin_license,
    requires=plugin_requires,
)

if additional_setup_parameters:
    from octoprint.util import dict_merge

    setup_parameters = dict_merge(setup_parameters, additional_setup_parameters)

setup(**setup_parameters)
