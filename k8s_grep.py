#!/usr/bin/env python3

import sys
import os
import shlex
import re

try:
    import yaml
    yaml.Loader.yaml_implicit_resolvers.pop("=") # Hack to fix pyyaml bug, see <https://github.com/yaml/pyyaml/issues/89#issuecomment-1124189214>
except ModuleNotFoundError:
    print("Error - Python YAML package is not installed, execute 'python -m pip install pyyaml' to install it and try again.")
    sys.exit(1)

from argparse import ArgumentParser
from subprocess import Popen, PIPE, TimeoutExpired
from os import walk as tree_walk
from collections.abc import Collection, Sequence, Mapping


def eprint(*args):
    ''' Wraper around print() that prints to stderr '''
    return print(*args, file=sys.stderr)


def stream_objects_from_cmd(command):
    ''' Generator function that returns a stream of k8s objects from the output of a command'''
    try:
        process = Popen(shlex.split(command), stdout=PIPE, stderr=PIPE ,universal_newlines=True)

        k8s_objects = yaml.safe_load_all(process.stdout)
        for k8s_object in k8s_objects:
            yield k8s_object

        process.wait(timeout=10)
    except TimeoutExpired as e:
        eprint(f"{command} stuck after {e.timeout}.\n {e.cmd} stderr: {e.stderr}\n\n killing {e.cmd} and exiting")
        process.kill()
        sys.exit(1)
    except OSError as e:
        eprint(f"Error executing {command}: {e.strerror}\n\nexiting.")
        sys.exit(1)


def stream_objects_from_dir(path, suffix='.yaml'):
    ''' Merges the yaml objects of all files in a directory tree that end with`suffix` into
        a single generator object '''

    def _handle_errors(e):
        raise e

    try:
        for dir_path, _, file_names in tree_walk(path, onerror=_handle_errors, followlinks=True):
            filterd_files = [f for f in file_names if f.endswith(suffix)]

            for file_name in filterd_files:
                with open(os.path.join(dir_path, file_name), mode='r', encoding='utf-8') as f:
                    k8s_objects = yaml.safe_load_all(f)

                    for k8s_object in k8s_objects:
                        yield k8s_object
    except OSError as e:
        eprint(f"Error scanning directory tree: {e.strerror}")
        if hasattr(e, 'filename'):
            eprint(f"File: {e.filename}")
        eprint('Exiting.')
        sys.exit(1)


def traverse_yaml_object(obj):
    ''' iterate over yaml object and return all scaler (simple leaf) values '''

    def _handle_subtree_dispatch(sub_obj):
        if isinstance(sub_obj, (Mapping, Sequence)) and not isinstance(sub_obj, str):
            yield from traverse_yaml_object(sub_obj)
        elif isinstance(sub_obj, Collection) and not isinstance(sub_obj, str):
            raise TypeError(f"Yaml object contains field of an unknown collection type: {type(sub_obj)}")
        else:
            yield sub_obj


    if isinstance(obj, Mapping):
        for v in obj.values():
            yield from _handle_subtree_dispatch(v)

    elif isinstance(obj, Sequence) and not isinstance(obj, str):
        for v in obj:
            yield from _handle_subtree_dispatch(v)

def match_yaml_object(regex, yaml_object):
    for yaml_leaf_node in traverse_yaml_object(yaml_object):
        if regex.search(str(yaml_leaf_node)):
            return True

    return False




def main():
    parser = ArgumentParser(usage='%(prog)s [options]')
    parser.add_argument("dir_path", action="store", default=None, nargs="?",
                        help="directory path to filter")
    parser.add_argument("-ks", "--kustomize", action="store_true", dest="kustomize",
                        help="Use kustomize to render the manifests before filtering")
    name_matcher = parser.add_mutually_exclusive_group()
    name_matcher.add_argument("-n","--name", action="append", dest="name", default=None,
                        help="filter by name - can be passed multiple times")
    name_matcher.add_argument("-xn", "--exclude-name", action="append", dest="xname", default=None,
                        help="exclude by name - can be passed multiple times")
    kind_matcher = parser.add_mutually_exclusive_group()
    kind_matcher.add_argument("-k", "--kind", action="append", dest="kind", default=None,
                        help="filter by kind - can be passed multiple times")
    kind_matcher.add_argument("-xk", "--exclude-kind", action="append", dest="xkind", default=None,
                        help="exclude by kind - can be passed multiple times")
    regex_matcher = parser.add_mutually_exclusive_group()
    regex_matcher.add_argument("-g", "--grep", action="append", dest="regex_lst", default=None,
                         help="filter by regexp match on yaml values (doesn't match keys) - can be passed multiple times")
    regex_matcher.add_argument("-xg", "--xgrep", action="append", dest="exclude_regex_lst", default=None,
                         help="exclude by regexp match on yaml values (doesn't match keys) - can be passed multiple times")
    args = parser.parse_args()

    if (args.regex_lst or args.exclude_regex_lst) is not None:
        try:
            if args.regex_lst is not None:
                compiled_regex_lst = tuple(re.compile(pattern) for pattern in args.regex_lst)
            else:
                compiled_regex_lst = tuple(re.compile(pattern) for pattern in args.exclude_regex_lst)
        except re.error as e:
            eprint(f"Regexp: \"{e.pattern}\" is invalid, error is: {e.msg}.\nExiting.")
            sys.exit(1)

    try:
        if args.dir_path is None and not sys.stdin.isatty():
            k8s_objects = yaml.safe_load_all(sys.stdin)
        elif args.kustomize:
            k8s_objects = stream_objects_from_cmd(f'kustomize build --enable-alpha-plugins --load-restrictor LoadRestrictionsNone {args.dir_path}') #TODO: make kustomize args configurable
        elif args.dir_path is not None:
            k8s_objects = stream_objects_from_dir(args.dir_path)
        else:
            raise RuntimeError('No manifest source provided, must have a directory, standard input or input from kustomize')
    except RuntimeError as e:
        if __name__ == '__main__':
            eprint(e.args[0])
            eprint('exiting.')
            sys.exit(1)
        else:
            raise


    matches = []
    for obj in k8s_objects:

        # All flags are logicly ANDed together, mutually exclusive flags are handled by the argument parser
        partial_matches = []
        if not ('kind' in obj and 'metadata' in obj and 'name' in obj['metadata']):
            eprint(f'Error in object {0}\nCould not find kind or metadata.name field!')
            sys.exit(1)

        if args.kind is not None:
            if any(k for k in args.kind if k.lower() == obj['kind'].lower()):
                partial_matches.append(True)
            else:
                partial_matches.append(False)

        if args.xkind is not None:
            if any(k for k in args.xkind if k.lower() != obj['kind'].lower()):
                partial_matches.append(True)
            else:
                partial_matches.append(False)

        if args.name is not None:
            if any(k for k in args.name if k.lower() == obj['metadata']['name'].lower()):
                partial_matches.append(True)
            else:
                partial_matches.append(False)

        if args.xname is not None:
            if any(k for k in args.xname if k.lower() != obj['metadata']['name'].lower()):
                partial_matches.append(True)
            else:
                partial_matches.append(False)

        if args.regex_lst is not None:
            if any(match_yaml_object(regex, obj) for regex in compiled_regex_lst):
                partial_matches.append(True)
            else:
                partial_matches.append(False)

        if args.exclude_regex_lst is not None:
            if not any(match_yaml_object(regex, obj) for regex in compiled_regex_lst):
                partial_matches.append(True)
            else:
                partial_matches.append(False)

        # match the object if all the partial matches are True
        if all(partial_matches): # all() does the right thing for us (returns True) if `partial_matches` is empty.
                                 # That handles the edge case where no matcher flags have been provided,
                                 # we want to match on all the objects in that case
            matches.append(obj)


    print(yaml.safe_dump_all(matches))

if __name__ == '__main__':
    sys.exit(main())
