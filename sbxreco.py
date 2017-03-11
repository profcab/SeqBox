#!/usr/bin/env python3

#--------------------------------------------------------------------------
# SBxReco - Sequenced Box container Recover
#s
# Created: 08/03/2017
#
# Copyright (C) 2017 Marco Pontello - http://mark0.net/
#
# Licence:
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#--------------------------------------------------------------------------

import os
import sys
import hashlib
import argparse
import binascii
from functools import partial
import sqlite3
from time import time

import seqbox

PROGRAM_VER = "0.8.0b"

BLOCKSIZE = 512

def banner():
    """Display the usual presentation, version, (C) notices, etc."""
    print("\nSeqBox - Sequenced Box container - Recover v%s" % (PROGRAM_VER),
          " - (C) 2017 by M.Pontello\n")


def get_cmdline():
    """Evaluate command line parameters, usage & help."""
    parser = argparse.ArgumentParser(
             description="recover SeqBox containers",
             formatter_class=argparse.ArgumentDefaultsHelpFormatter,
             prefix_chars='-+')
    parser.add_argument("-v", "--version", action='version', 
                        version='SBxRecover v%s' % PROGRAM_VER)
    parser.add_argument("dbfilename", action="store", metavar="filename",
                        help="database with recovery info")
    parser.add_argument("destpath", action="store", nargs="?", metavar="path",
                        help="destination path for recovered sbx files")
    parser.add_argument("-file", action="store", nargs="+", metavar="filename",
                        help="original filename(s) to recover")
    parser.add_argument("-sbx", action="store", nargs="+", metavar="filename",
                        help="SBx filename(s) to recover")
    parser.add_argument("-uid", action="store", nargs="+", metavar="uid",
                        help="UID(s) to recover")
    parser.add_argument("-all", action="store_true", help="recover all")
    parser.add_argument("-i", "--info", action="store_true", default=False,
                        help="show info on recoverable sbx file(s)")
    parser.add_argument("-o", "--overwrite", action="store_true", default=False,
                        help="overwrite existing sbx file(s)")
    res = parser.parse_args()
    return res


def errexit(errlev=1, mess=""):
    """Display an error and exit."""
    if mess != "":
        print("%s: error: %s" % (os.path.split(sys.argv[0])[1], mess))
    sys.exit(errlev)


def dbGetMetaFromUID(c, uid):
    meta = {}
    c.execute("SELECT * from sbx_meta where uid = '%i'" % uid)
    res = c.fetchone()
    if res:
        meta["filesize"] = res[1]
        meta["filename"] = res[2]
        meta["sbxname"] = res[3]
    return meta

def dbGetUIDFromFileName(c, filename):
    c.execute("select uid from sbx_meta where name = '%s'" % (filename))
    res = c.fetchone()
    if res:
        return(res[0])

def dbGetUIDFromSbxName(c, sbxname):
    c.execute("select uid from sbx_meta where sbxname = '%s'" % (sbxname))
    res = c.fetchone()
    if res:
        return(res[0])

def dbGetBlocksCountFromUID(c, uid):
    c.execute("SELECT uid from sbx_blocks where uid = '%i' group by num order by num" % (uid))
    return len(c.fetchall())

def dbGetBlocksListFromUID(c, uid):
    c.execute("SELECT num, fileid, pos from sbx_blocks where uid = '%i' group by num order by num" % (uid))
    return c.fetchall()

def dbGetUIDsList(c):
    c.execute("SELECT uid from sbx_blocks GROUP BY uid")
    res = [row[0] for row in c.fetchall()]
    return res

def dbGetSourcesList(c):
    c.execute("SELECT * FROM sbx_source")
    return c.fetchall()


def uniquifyFileName(filename):
    count = 0
    uniq = ""
    name,ext = os.path.splitext(filename)
    while os.path.exists(filename):
        count += 1
        uniq = "(%i)" % count
        filename = name + uniq + ext
    return filename


def report(c):
    """Create a detailed report with the info obtained by SbxScan"""
    #test
    c.execute("SELECT uid from sbx_blocks group by uid order by uid")
    for row in c.fetchall():
        uid = row[0]
        hexdigits = binascii.hexlify(uid.to_bytes(6, byteorder="big")).decode()
        metadata = dbGetMetaFromUID(c, uid)
        blocksnum = dbGetBlocksCountFromUID(c, uid)
        filename = metadata["filename"] if "filename" in metadata else ""
        sbxname = metadata["sbxname"] if "sbxname" in metadata else ""

        if "filesize" in metadata:
            filesize = metadata["filesize"]
            est = ""
        else:
            filesize = blocksnum * BLOCKSIZE
            est = chr(126)
        
        print("%s %i %i%s '%s'" % (hexdigits, blocksnum, filesize, est, sbxname))

def main():

    banner()
    cmdline = get_cmdline()

    dbfilename = cmdline.dbfilename
    if not os.path.exists(dbfilename) or os.path.isdir(dbfilename):
        errexit(1,"file '%s' not found!" % (dbfilename))

    #open database
    print("opening '%s' database..." % (dbfilename))
    conn = sqlite3.connect(dbfilename)
    c = conn.cursor()

    if cmdline.info:
        report(c)
        errexit(0)

    #build a list of uid to recover:
    uid_list = []
    if cmdline.all:
        uid_list = dbGetUIDsList(c)
    else:
        if cmdline.uid:
            for hexuid in cmdline.uid:
                if len(hexuid) % 2 != 0:
                    errexit(1, "invalid UID!")
                uid = int.from_bytes(binascii.unhexlify(hexuid),
                                     byteorder="big")
                if dbGetBlocksCountFromUID(c, uid):
                    uid_list.append(uid)
                else:
                    errexit(1,"no recoverable UID '%s'" % (hexuid))
        if cmdline.sbx:
            for sbxname in cmdline.sbx:
                uid = dbGetUIDFromSbxName(c, sbxname)
                if uid:
                    uid_list.append(uid)
                else:
                    errexit(1,"no recoverable sbx file '%s'" % (sbxname))
        if cmdline.file:
            for filename in cmdline.file:
                uid = dbGetUIDFromFileName(c, filename)
                if uid:
                    uid_list.append(uid)
                else:
                    errexit(1,"no recoverable file '%s'" % (filename))

    if len(uid_list) == 0:
        errexit(1, "nothing to recover!")

    print("recovering SBx files...")
    uid_list = sorted(set(uid_list))

    #open all the sources
    finlist = {}
    for key, value in dbGetSourcesList(c):
        finlist[key] = open(value, "rb")

    uidcount = 0
    for uid in uid_list:
        uidcount += 1
        hexuid = binascii.hexlify(uid.to_bytes(6, byteorder="big")).decode()
        print("UID %s (%i/%i)" % (hexuid, uidcount, len(uid_list)))

        blocksnum = dbGetBlocksCountFromUID(c, uid)
        print("  blocks: %i - size: %i bytes" %
              (blocksnum, blocksnum * BLOCKSIZE))
        meta = dbGetMetaFromUID(c, uid)
        if "sbxname" in meta:
            sbxname = meta["sbxname"]
        else:
            #use hex uid as name if no metadata present
            sbxname = (binascii.hexlify(uid.to_bytes(6, byteorder="big")).decode() +
                       ".sbx")
        if cmdline.destpath:
            sbxname = os.path.join(cmdline.destpath, sbxname)
        print("  to: '%s'" % sbxname)

        if not cmdline.overwrite:
            sbxname = uniquifyFileName(sbxname)
        fout = open(sbxname, "wb", buffering = 1024*1024)

        blockdatalist = dbGetBlocksListFromUID(c, uid)
        #read 1 block to initialize the correct block parameters
        #(needed for filling in missing blocks)
        blockdata = blockdatalist[0]
        sbx = seqbox.sbxBlock()
        fin = finlist[blockdata[1]]
        bpos = blockdata[2]
        fin.seek(bpos, 0)
        sbx.decode(fin.read(BLOCKSIZE))
        
        lastblock = -1
        ticks = 0
        missingblocks = 0
        updatetime = time() -1
        maxbnum =  blockdatalist[-1][0]
        for blockdata in blockdatalist:
            bnum = blockdata[0]
            #check for missing blocks and fill in
            if bnum != lastblock +1 and bnum != 1:
                for b in range(lastblock+1, bnum):
                    sbx.blocknum = b
                    sbx.data = bytes(sbx.datasize)
                    buffer = sbx.encode()
                    fout.write(buffer)
                    missingblocks += 1

            fin = finlist[blockdata[1]]
            bpos = blockdata[2]
            fin.seek(bpos, 0)
            buffer = fin.read(BLOCKSIZE)
            fout.write(buffer)
            lastblock = bnum

            #some progress report
            if time() > updatetime or bnum > len(blockdatalist):
                print("  %.1f%%" % (bnum*100.0/maxbnum), " ",
                      "(missing blocks: %i)" % missingblocks,
                      end="\r", flush=True)
                updatetime = time() + .5

        fout.close()
        print()



if __name__ == '__main__':
    main()
