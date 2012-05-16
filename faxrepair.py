# -*- coding:utf-8 -*-

'''Tries to recover damaged PDF files received by the Fritz!Box.
These files have one in common: They are missing a trailer and the pages directive.
Everything after the main body even, more precisely.
This program checks the references to the pages directive and reconstructs it,
as well as the xref-container and the trailer.

Disclaimer:
JUST A QUICK HACK!

TODO:
  - More meaningful docstrings, descriptions of what happens
  

  
Copyright (c) 2012 Maurice-Pascal Sonnemann (msonnemann@online.de)

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

'''

import sys
import os
import re
import argparse

class UnrecoverableDamage(RuntimeError):
    pass


class FaxPDFRepair(object):
    
    def __init__(self, src):
        '''Constructs a repairer that builds a valid PDF from damaged input.
        
        Arguments:
        src: Raw content of damaged PDF. Either a byte-string or an object
             exposing a file-like interface.
        '''
        
        # Duck-typing: File-like?
        if hasattr(src, 'read'):
            # src is a file, read all into memory
            src = src.read()
        
        self.src = src
        self.output = None
    
    
    def xref_is_missing(self):
        '''Warning: No escaping, if some one writes about xrefs then you are in trouble
        '''
        return not any(('xref' in line for line in self.src.splitlines()))
    
    def trailer_is_missing(self):
        '''Warning: No escaping, if some one writes about trailers then you are in trouble
        '''
        return not any(('trailer' in line for line in self.src.splitlines()))
    
    def pages_is_missing(self):
        # Pages is missing when there are no such objects
        return len(self.find_obj("/Pages")) == 0
    
    def object_offsets(self):
        '''Returns array of dictionaries, where each dictionary has the following entries:
        id : ID of the object
        gen: Generation of the object
        idx: Offset of the object in source
        contents: contents of the object
        '''
        
        source = self.src
        
        objects = []
        idx = 0
        lines = source.splitlines(True) # keep line-ends
        for i, line in enumerate(lines):
            match = re.match("\s*(\d+)\s+(\d+)\s+obj", line)
            if match:
                # find endobj line
                offset = line.find(match.group(1))
                endobj_lineno = source.splitlines(False).index("endobj", i) # start searching from current line
                objects.append({
                        "id": match.group(1),
                        "gen": match.group(2),
                        "idx": idx + offset,
                        "contents": "".join(lines[i:endobj_lineno + 1])
                    })
            idx += len(line)
        return objects
    
    def construct_xref(self, holes=None):
        
        source = self.src
    
        holes = holes if holes is not None else []
        
        result = ["xref", ]
        
        objs = self.object_offsets()
        
        result.append("0 {count}".format(count=len(objs) + 1))
        result.append("0000000000 65535 f ") # zeroth object
        
        obj_dict = {}
        for obj in objs:
            obj_dict[int(obj["id"])] = obj
        
        if len(obj_dict.keys()) <> max(obj_dict.keys()):
            raise RuntimeError("Holes in the object table! Run check_holes before this!")
        
        for key in sorted(obj_dict.keys()):
            obj = obj_dict[key]
            if key in holes:
                usemode = "f" # not in use / free
            else:
                usemode = "n" # in use
            result.append("{0:010} {1:05} {2} ".format(int(obj["idx"]), 0, usemode))
        
        return "\n".join([''] + result)
    
    def check_holes(self):
        source = self.src
        objs = self.object_offsets()
        obj_dict = {}
        for obj in objs:
            obj_dict[int(obj["id"])] = obj
        
        holes = []
        stubs = []
        if len(obj_dict.keys()) <> max(obj_dict.keys()):
            # Problem: Objects are not consecutively numbered.
            # Solution: Find holes, create stub objects, set them as not-in-use.
            for i in range(1, max(obj_dict.keys()) + 1):
                if not i in obj_dict.keys(): # doesn't exist as indirect object, but is referenced
                    holes.append(i)
                    # Create stub object
                    stubs.append("{0} 0 obj".format(i))
                    stubs.append("-1")
                    stubs.append("endobj")
        return "\n".join([''] + stubs), holes
    
    def construct_trailer(self):
        source = self.src
        lines = source.splitlines(True)
        xref_lineno = source.splitlines(False).index("xref")
        startxref = sum([len(line) for line in lines[:xref_lineno]])
        result = ["trailer",
                  "<< /Size {0}".format(len(self.object_offsets())),
                  "/Root {0} 0 R".format(self.find_obj("/Catalog")[0]["id"]),
                  "/Info {0} 0 R".format(self.find_info_obj()["id"]),
                  ">>",
                  "startxref",
                  "{0}".format(startxref),
                  "%%EOF"]
        return "\n".join([''] + result)
    
    

    def construct_pages(self):
        # First, get object-id for the PAGES object to be constructed. The id is contained in the /Catalog
        catalog = self.find_obj("/Catalog")[0]
        idx_start = catalog["contents"].find("/Pages")
        idx_end = catalog["contents"].find("R", idx_start)
        substring = catalog["contents"][idx_start:idx_end + 1]
        parts = substring.split()
        page_id = parts[1]
        page_gen = parts[2]
        
        subpages = self.find_obj("/Page")
        page_refs = " ".join([ "{0} {1} R".format(id, gen) for (id, gen) in [ (obj["id"], obj["gen"]) for obj in subpages] ])
        
        result = ["{id} {gen} obj".format(id=page_id, gen=page_gen),
                  "<< /Type /Pages",
                  "/Kids [ {refs} ]".format(refs=page_refs),
                  "/Count {count}".format(count=len(subpages)),
                  ">>",
                  "endobj"]
                  
        return "\n".join([''] + result)

    def obj_type(self, src):
        '''Returns type of object, which is described in source'''
        parts = src.split()
        if "/Type" in parts:
            return parts[parts.index("/Type") + 1]
        else:
            return None
    
    def find_obj(self, obj_t):
        '''Returns array of IDs of objects of given type'''
        objects = []
        for obj in self.object_offsets():
            if self.obj_type(obj["contents"]) == obj_t:
                objects.append(obj)
        return objects
    
    def find_info_obj(self):
        '''Searches info object in source and returns it or None'''
        for obj in self.object_offsets():
            if all([ x in obj["contents"] for x in ("/Title", "/Creator") ]):
                return obj
        return None

    def recover(self):
        
        if not self.trailer_is_missing():
            raise UnrecoverableDamage("File trailer exists already. I do not\
                                       know how to continue.")
        
        orig_src = self.src[:]
        
        if self.pages_is_missing():
           self.src += self.construct_pages()
        if self.xref_is_missing():
            stubs, holes = self.check_holes()
            self.src += stubs
            self.src += self.construct_xref(holes)
        
        self.src += self.construct_trailer()
        
        self.output = self.src
        self.src = orig_src
        
        # Make chaining possible
        return self


def status(msg):
    print >> sys.stderr, msg

def main():
    parser = argparse.ArgumentParser(description='Repairs damaged PDFs created by the Fritz!Box fax machine.')
    parser.add_argument('--verbose', action='store_true', help='Enable diagnostical message reporting on stderr.')
    parser.add_argument('infile', nargs='?', type=argparse.FileType('r'), default=sys.stdin, help='Filename of damaged input file. Omit to use stdin as PDF source.')
    parser.add_argument('outfile', nargs='?', type=argparse.FileType('w'), default=sys.stdout, help='Filename of valid PDF to be written. Omit to use stdout as PDF sink.')
    args = parser.parse_args()
    
    repairer = FaxPDFRepair(args.infile)
    if args.verbose:
        status('Missing parts:')
        if repairer.trailer_is_missing():
            status('\tTrailer')
        if repairer.pages_is_missing():
            status('\tPages')
        if repairer.xref_is_missing():
            status('\tXref')
        status('Starting to repair')
    try:
        repairer.recover()
        if args.verbose: status('Repair successful.')
    except UnrecoverableDamage as e:
        status('Repair unsuccessful:')
        status(repr(e))
        sys.exit(1)
    args.outfile.write(repairer.output)

if __name__ == "__main__":
    main()
