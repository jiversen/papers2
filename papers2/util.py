import json
import os
import pickle
import re
import sys
import logging as log

from argparse import ArgumentParser
from configparser import SafeConfigParser as ConfigParser


def read_property_file(f, defaults=None):
    config = ConfigParser(defaults)
    config.read(f)
    return config


def parse_with_config(add_args, sections, short_name="c", long_name="config", 
        default=None, help="Configuration file", **kwargs):
    pre_parser = ArgumentParser(add_help=False)
    pre_parser.add_argument("-{0}".format(short_name), "--{0}".format(long_name), default=default)
    args, rest = pre_parser.parse_known_args()
    defaults = {}
    if args.config is not None:
        config = ConfigParser()
        config.read(args.config)
        for section in sections:
            defaults.update(config.items(section))

    parser = ArgumentParser()
    parser.add_argument("-{0}".format(short_name), "--{0}".format(long_name),
        default=default, help=help, **kwargs)
    add_args(parser)
    parser.set_defaults(**defaults)
    args = parser.parse_args(args=rest)
    return args


class Batch(object):
    def __init__(self, max_size):
        self.items = []
        self.notes = []
        self.attachments = []
        self.max_size = max_size
    
    @property
    def size(self):
        return len(self.items)
    
    @property
    def is_full(self):
        return self.size >= self.max_size
    
    @property
    def is_empty(self):
        return len(self.items) == 0
    
    def add(self, item, notes, attachments):
        self.items.append(item)
        self.notes.append(notes)
        self.attachments.append(attachments)

    def iter(self):
        for item in zip(self.items, self.notes, self.attachments):
            yield item
    
    def clear(self):
        self.rowids = []
        self.items = []
        self.notes = []
        self.attachments = []


# Simple checkpointing facility that maintains a
# set of items IDs and pickles them on commit.
class Checkpoint(object):
    def __init__(self, filename):
        self.filename = filename
        if os.path.exists(filename):
            with open(filename, "rb") as i:
                tmp = pickle.load(i)
                self.ids, self.failed = tmp
        else:
            self.ids = set()
            self.failed = set()
        self._uncommitted = []
    
    def add(self, db_id):
        self._uncommitted.append(db_id)
        self.failed.discard(db_id) # we're giving it another chance
    
    def remove(self, db_idx):
        del self._uncommitted[db_idx]

    def get(self, db_idx):
        return self._uncommitted[db_idx]

    def add_failed(self, db_id):
        self.failed.add(db_id)
    
    def commit(self):
        to_commit = (id for id in self._uncommitted if id not in self.failed)
        self.ids.update(to_commit)
        with open(self.filename, 'wb') as o:
            pickle.dump((self.ids, self.failed), o)
        self._uncommitted = []

    def rollback(self):
        self._uncommitted = []
    
    def contains(self, db_id):
        return db_id in self.ids

    def contains_failed(self, db_id):
        return db_id in self.failed


# Create an enumerated type
def enum(name, **enums):
    _enums = enums.copy()
    _enums["__names__"] = list(n for n in list(enums.keys()))
    _enums["__values__"] = list(v for v in list(enums.values()))
    _enums["__reverse_dict__"] = dict((value, key) for key,value in enums.items())
    return type(name, (), _enums)


class JSONWriter(object):
    def __init__(self, file):
        self._fh = sys.stdout if file == "stdout" else open(file, "w")
    
    def close(self):
        if self._fh != sys.stdout:
            self._fh.close()
    
    def write(self, item, notes=None, attachments=None):
        self._fh.write("ITEM:\n")
        self._fh.write(json.dumps(item, indent=4, separators=(',', ': ')))
        self._fh.write("\n")

        if notes is not None:
            self._fh.write("NOTES:\n")
            self._fh.write(json.dumps(notes, indent=4, separators=(',', ': ')))
            self._fh.write("\n")

        if attachments is not None:
            self._fh.write("ATTACHMENTS:\n")
            self._fh.write(json.dumps(attachments, indent=4, separators=(',', ': ')))
            self._fh.write("\n")
