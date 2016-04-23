#!/usr/bin/env python3

##
# Copyright 2016 Andrey Mrichko <andymrk2@gmail.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
##

from pathlib import Path
import argparse
import sqlite3
import glob
import os
import sys
from configparser import ConfigParser
from sh import ls

__version__=0.6

def resolve_path(func):
    def wrapper(self, tags, objects, flags):
        robjects = []
        if flags["recursive"]:
            for o in objects:
                if Path(o).is_absolute() and Path(o).is_dir():
                    pattern = str(Path(o) / '**')
                elif Path(o).is_absolute():
                    pattern=o
                else:
                    pattern = '**/'+o
                robjects += glob.iglob(pattern, recursive=True)
        else:
            for o in objects:
                robjects += glob.iglob(o)
        if flags["files_only"] or flags["dirs_only"]:
            type_filter = lambda x: Path(x).is_file() if flags["files_only"] else Path(x).is_dir()
            robjects = [str(Path(obj).resolve()) for obj in robjects if type_filter(obj)]
        else:
            robjects = [str(Path(obj).resolve()) for obj in robjects]
        robjects = list(set(robjects))
        if flags["verbose"]: print("Pattern(s) was resolved to file(s)/dir(s): %s" % ', '.join(robjects), file=sys.stderr)
        func(self, tags=tags, objects=robjects, flags=flags)
    return wrapper

def pretty_print(func):
    def wrapper(self, data, flags):
        res = func(self, data, flags=flags)
        endl = False
        if flags["ll"]: print("total %d" % len(res))
        for o in res:
            if isinstance(o, str):
                if flags["ll"]:
                    print(ls("-l", "-d", o), end='')
                else:
                    print(o, end=' ')
                    endl = True
            else:
                if flags["ll"]:
                    ls_out = str(ls("-l", "-d", o[0]))
                    print(ls_out[:-1], o[1])
                else:
                    print(' '.join(o))
        if endl: print()
    return wrapper

class Tagger(object):

    config = None
    db_path = "~/tagger.db"

    def __init__(self, verbose):
        # find config
        if Path("~/.tagger.conf").expanduser().exists():
            self.config = str(Path("~/.tagger.conf").expanduser().resolve())
            if verbose: print("Use user config: %s " % self.config, file=sys.stderr)
        elif Path("/etc/tagger.conf").resolve().exists():
            self.config = str(Path("~/.tagger.conf").resolve())
            if verbose: print("Use system config: %s " % self.config, file=sys.stderr)
        else:
            if verbose: print("Config not found. Use default settings", file=sys.stderr)
        # read config
        if self.config:
            settings = ConfigParser()
            settings.read(self.config)
            if "db_path" in settings["default"]:
                self.db_path = settings["default"]["db_path"]
            self.db_path = str(Path(self.db_path).expanduser())
        # connect to db
        if verbose: print("DB path is %s" % self.db_path, file=sys.stderr)
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.cur = self.conn.cursor()
            self.__init_db()
        except sqlite3.OperationalError as e:
            print("Can't access database %s: %s" % (self.db_path, e))
            sys.exit(1)

    def __init_db(self):
        sql = "SELECT name FROM sqlite_master WHERE type='table' AND name='tags'"
        self.cur.execute(sql)
        if not self.cur.fetchone():
            init_sql = "CREATE TABLE tags ( \
                        id INTEGER PRIMARY KEY NOT NULL, \
                        tag CHAR(255) NOT NULL, \
                        parent CHAR(1024) NOT NULL, \
                        object CHAR(1024) NOT NULL, \
                        is_dir INTEGER DEFAULT 0)"
            self.cur.execute(init_sql)
            self.conn.commit()

    def show_tags(self):
        self.cur.execute('SELECT DISTINCT tag FROM tags')
        tags = [row[0] for row in self.cur.fetchall()]
        print('\n'.join(tags))

    @resolve_path
    def add(self, tags, objects, flags):
        for tag in tags:
            if flags["verbose"]: print("Added tag '%s' to file(s)/dirs(s): %s" % (tag, ', '.join(objects)), file=sys.stderr)
            tag_data = [(tag, str(Path(obj).parent), obj, Path(obj).is_dir()) for obj in objects]
            self.cur.executemany('INSERT INTO tags (tag, parent, object, is_dir) VALUES (?,?,?,?)', tag_data)
            self.conn.commit()

    @resolve_path
    def list(self, objects, tags, flags):
        if objects:
            self.list_objects(objects, flags)
        elif tags:
            self.list_tags(tags, flags)
        else:
            print("There is no such file or directory", file=sys.stderr)
            sys.exit(2)

    @pretty_print
    def list_tags(self, tags, flags):
        if flags["verbose"]: print("Print file(s)/dir(s) that have following tags: %s" % ", ".join(tags), file=sys.stderr)
        cur_dir = str(Path().resolve())
        if flags["files_only"]:
            sql_suffix = "and is_dir=0"
        elif flags["dirs_only"]:
            sql_suffix = "and is_dir=1"
        else:
            sql_suffix = ""
        if flags["all"]:
            sql = "SELECT object FROM tags WHERE tag in (%s) %s GROUP BY object" % (', '.join("?" for _ in tags), sql_suffix)
            self.cur.execute(sql, tags)
            objects = [o[0] for o in self.cur.fetchall() if Path(o[0]).exists()]
            return objects
        elif flags["recursive"]:
            sql = 'SELECT object FROM tags WHERE tag in (%s) and instr(parent, ?) = 1 %s GROUP BY object' % (', '.join("?" for _ in tags), sql_suffix)
            self.cur.execute(sql, (*tags, cur_dir) )
            objects = [str(Path(o[0]).relative_to(cur_dir)) for o in self.cur.fetchall() if Path(o[0]).exists()]
            return objects
        else:
            sql = "SELECT object FROM tags WHERE tag in (%s) and parent=? %s GROUP BY object" % (', '.join("?" for _ in tags), sql_suffix)
            self.cur.execute(sql, (*tags, cur_dir) )
            objects = [Path(o[0]).name for o in self.cur.fetchall() if Path(o[0]).exists()]
            return objects

    @pretty_print
    def list_objects(self, objects, flags):
        cur_dir = str(Path().resolve())
        if flags["verbose"]: print("Print tags for following file(s)/dir(s): %s" % ", ".join(objects), file=sys.stderr)
        sql = 'SELECT object, GROUP_CONCAT(tag) FROM tags WHERE object in (%s) GROUP BY object' % ', '.join("?" for _ in objects)
        self.cur.execute(sql, objects)
        res = [(str(Path(obj[0])), obj[1] ) for obj in self.cur.fetchall() if Path(obj[0]).exists()]
        return res

    @resolve_path
    def remove(self, tags, objects, flags):
        if tags and objects:
            print("Remove tag(s) '%s' from file(s)/dir(s): %s? (y/N)" % (", ".join(tags), ', '.join(objects) ), file=sys.stderr, end=' ')
            if input() in ('y', 'Y'):
                sql = "DELETE FROM tags WHERE tag in (%s) and object in (%s)" % \
                      (', '.join("?" for _ in tags), ', '.join("?" for _ in objects))
                self.cur.execute(sql, (*tags, *objects) )
                self.conn.commit()
        elif objects:
            print("Remove all tags from file(s)/dir(s): %s? (y/N)" % ', '.join(objects), file=sys.stderr, end=' ')
            if input() in ('y', 'Y'):
                sql = "DELETE FROM tags WHERE object in (%s)" % ', '.join("?" for _ in objects)
                self.cur.execute(sql, objects)
                self.conn.commit()
        elif tags:
            suffix = ""
            if flags["files_only"]:
                suffix = " from all files"
                flag = 0
            if flags["dirs_only"]:
                suffix = " from all dirs"
                flag = 1
            print("Remove tag(s) '%s'%s? (y/N)" % ("', '".join(tags), suffix), file=sys.stderr, end=' ')
            if input() in ('y', 'Y'):
                if flags["files_only"] or flags["dirs_only"]:
                    sql = "DELETE FROM tags WHERE tag in (%s) AND is_dir=?" % ', '.join("?" for _ in tags)
                    self.cur.execute(sql, (*tags, flag))
                else:
                    sql = "DELETE FROM tags WHERE tag in (%s)" % ', '.join("?" for _ in tags)
                    self.cur.execute(sql, tags)
                self.conn.commit()
        else:
            pass

#-------------------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description='Tool for tag your files or directories')
    parser.add_argument('-A', action='store_true', help='show all tags and exist')
    parser.add_argument('-D', "--delete", action='store_true', help='delete tag(s) from file(s) or folder(s)')
    parser.add_argument('-a', "--all", action='store_true', help='print all files/directories with tags (by default only from current dir)')
    parser.add_argument('-l', '--ls', action='store_true', help="extended output information (Like 'ls -l')")
    parser.add_argument('-r', "--recursive", action='store_true', help='manage tag(s) recursivelly')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-d', "--directories", action='store_true', help='Manage only directories')
    group.add_argument('-f', "--files", action='store_true', help='Manage only files')
    parser.add_argument('-v', "--verbose", action='store_true', help='increase output verbosity')
    parser.add_argument('pattern', type=str, nargs='*', help='list of files, directories or glob that you want to tag')
    parser.add_argument('-t', '--tags', type=str, nargs='*', help='tag(s) that you want set to file(s) or folder(s)')
    args = parser.parse_args()
    if args.verbose: print("Received parameters: %s" % args, file=sys.stderr)
    if args.A:
        Tagger(args.verbose).show_tags()
        sys.exit(0)

    flags = {"all": args.all, "recursive": args.recursive, "verbose": args.verbose, 
             "ll": args.ls, "files_only": args.files, "dirs_only": args.directories}
    T = Tagger(args.verbose)
    if args.delete:
        T.remove(tags=args.tags, objects=args.pattern, flags=flags)
    elif args.tags and args.pattern:
        T.add(tags=args.tags, objects=args.pattern, flags=flags)
    elif args.tags or args.pattern:
        T.list(tags=args.tags, objects=args.pattern, flags=flags)
    else:
        parser.print_help()

def lstag():
    parser = argparse.ArgumentParser(description='Tagger alias for show file(s) or folder(s) with specified tag(s)')
    parser.add_argument('-A', action='store_true', help='show all tags and exist')
    parser.add_argument('-a', "--all", action='store_true', help='print all file(s)/dir(s) with specified tags (by default only from current dir)')
    parser.add_argument('-l', '--ls', action='store_true', help="extended output information (Like 'ls -l')")
    parser.add_argument('-r', "--recursive", action='store_true', help='manage tag(s) recursivelly')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-d', "--directories", action='store_true', help='Manage only directories')
    group.add_argument('-f', "--files", action='store_true', help='Manage only files')
    parser.add_argument('-v', "--verbose", action='store_true', help='increase output verbosity')
    parser.add_argument('tags', type=str, nargs='*', help='tag(s) that should contain file(s) or folder(s)')
    args = parser.parse_args()
    if args.verbose: print("Received parameters: %s" % args, file=sys.stderr)
    if args.A:
        Tagger(args.verbose).show_tags()
        sys.exit(0)

    flags = {"all": args.all, "recursive": args.recursive, "verbose": args.verbose, 
             "ll": args.ls, "files_only": args.files, "dirs_only": args.directories}
    T = Tagger(args.verbose)
    if args.tags:
        T.list(tags=args.tags, objects=[], flags=flags)
    else:
        parser.print_help()

def lsotag():
    parser = argparse.ArgumentParser(description='Tagger alias for show tags of specified file(s) or folder(s)')
    parser.add_argument('-l', '--ls', action='store_true', help="extended output information (Like 'ls -l')")
    parser.add_argument('-r', "--recursive", action='store_true', help='manage file(s)/folder(s) recursivelly')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-d', "--directories", action='store_true', help='Manage only directories')
    group.add_argument('-f', "--files", action='store_true', help='Manage only files')
    parser.add_argument('-v', "--verbose", action='store_true', help='increase output verbosity')
    parser.add_argument('pattern', type=str, nargs='*', help='file(s) or dir(s) for which you want to see tags')
    args = parser.parse_args()
    if args.verbose: print("Received parameters: %s" % args, file=sys.stderr)

    flags = {"recursive": args.recursive, "verbose": args.verbose, "ll": args.ls,
             "files_only": args.files, "dirs_only": args.directories}
    T = Tagger(args.verbose)
    if args.pattern:
        T.list(tags=[], objects=args.pattern, flags=flags)
    else:
        parser.print_help()

def tag():
    parser = argparse.ArgumentParser(description='Tagger alias for setting tags to specified files(s) or folder(s)')
    parser.add_argument('-r', "--recursive", action='store_true', help='manage file(s)/dir(s) recursivelly')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-d', "--directories", action='store_true', help='Manage only directories')
    group.add_argument('-f', "--files", action='store_true', help='Manage only files')
    parser.add_argument('-v', "--verbose", action='store_true', help='increase output verbosity')
    parser.add_argument('pattern', type=str, nargs='+', help='file(s), dir(s) or glob for which you want set tags')
    parser.add_argument('-t', '--tags', type=str, nargs='+', help='tag(s) that you want set to file(s)/dir(s)', required=True)
    args = parser.parse_args()
    if args.verbose: print("Received parameters: %s" % args, file=sys.stderr)

    flags = {"recursive": args.recursive, "verbose": args.verbose, "files_only": args.files, "dirs_only": args.directories}
    T = Tagger(args.verbose)
    if args.pattern and args.tags:
        T.add(tags=args.tags, objects=args.pattern, flags=flags)
    else:
        parser.print_help()

def rmtag():
    parser = argparse.ArgumentParser(description='Tagger alias for removing tags from specified file(s) or folder(s)')
    parser.add_argument('-r', "--recursive", action='store_true', help='manage file(s)/dir(s) recursivelly')
    parser.add_argument('-v', "--verbose", action='store_true', help='increase output verbosity')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-d', "--directories", action='store_true', help='Manage only directories')
    group.add_argument('-f', "--files", action='store_true', help='Manage only files')
    parser.add_argument('pattern', type=str, nargs='*', help='file(s), dir(s) or glob for which you want remove tags')
    parser.add_argument('-t', '--tags', type=str, nargs='*', help='tag(s) that you want remove from file(s) or dir(s)')
    args = parser.parse_args()
    if args.verbose: print("Received parameters: %s" % args, file=sys.stderr)

    flags = {"recursive": args.recursive, "verbose": args.verbose, "files_only": args.files, "dirs_only": args.directories}
    T = Tagger(args.verbose)
    if args.pattern or args.tags:
        T.remove(tags=args.tags, objects=args.pattern, flags=flags)
    else:
        parser.print_help()


if __name__ == "__main__":
    alias = os.path.basename(__file__)
    if alias == "lstag":
        lstag()
    elif alias == "lsotag":
        lsotag()
    elif alias == "tag":
        tag()
    elif alias == "rmtag":
        rmtag()
    else:
        main()
