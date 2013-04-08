#!/usr/bin/env python
# Copyright 2012 Google Inc. All Rights Reserved.

"""Tests for grr.lib.flows.general.grep."""



from grr.client import vfs
from grr.client.client_actions import searching
from grr.lib import aff4
from grr.lib import data_store
from grr.lib import rdfvalue
from grr.lib import test_lib
from grr.lib import type_info


class TestGrepFlow(test_lib.FlowTestsBaseclass):

  def FlushVFSCache(self):
    test_lib.ClientVFSHandlerFixture.cache = {}

  def CreateFile(self, filename, data):

    # Delete the fixture cache so this will be included.
    self.FlushVFSCache()

    test_lib.client_fixture.VFS.append(
        (filename,
         ("VFSFile",
          {"aff4:stat": (
              "\n"
              "st_mode: 33261\n"
              "st_ino: 1026267\n"
              "st_dev: 51713\n"
              "st_nlink: 1\n"
              "st_uid: 0\n"
              "st_gid: 0\n"
              "st_size: 60064\n"
              "st_atime: 1308964274\n"
              "st_mtime: 1285093975\n"
              "st_ctime: 1299502221\n"
              "st_blocks: 128\n"
              "st_blksize: 4096\n"
              "st_rdev: 0\n"
              "pathspec {\n"
              "  pathtype: OS\n"
              "  path: '%s'\n"
              "}\n"
              "resident: '%s'\n" % (filename, data)),
           "aff4:size": len(data),
          })))

  def DeleteFile(self, filename):

    # Delete the fixture cache so this will be included.
    self.FlushVFSCache()

    test_lib.client_fixture.VFS = [path for path in test_lib.client_fixture.VFS
                                   if path[0] != filename]

  def setUp(self):
    super(TestGrepFlow, self).setUp()

    # Install the mock
    vfs.VFS_HANDLERS[
        rdfvalue.RDFPathSpec.Enum("OS")] = test_lib.ClientVFSHandlerFixture
    self.client_mock = test_lib.ActionMock("Grep")

  def testNormalGrep(self):

    output_path = "analysis/grep1"

    grepspec = rdfvalue.GrepSpec(mode=rdfvalue.GrepSpec.Enum("FIRST_HIT"),
                                 literal="hello")

    grepspec.target.path = "/proc/10/cmdline"
    grepspec.target.pathtype = rdfvalue.RDFPathSpec.Enum("OS")

    for _ in test_lib.TestFlowHelper(
        "Grep", self.client_mock, client_id=self.client_id,
        token=self.token, output=output_path, request=grepspec):
      pass

    # Check the output file is created
    fd = aff4.FACTORY.Open("aff4:/{0}/{1}".format(self.client_id,
                                                  output_path),
                           token=self.token)
    hits = fd.Get(fd.Schema.HITS)

    self.assertEqual(len(hits), 1)
    self.assertEqual(hits[0].offset, 3)
    self.assertEqual(hits[0], "ls\x00hello world\'\x00-l")
    self.assertEqual(hits[0].length, 18)

  def testMultipleHits(self):
    filename = "/fs/os/c/Downloads/grepfile.txt"
    data = "random content here. I am a HIT!!" * 100

    self.CreateFile(filename, data)

    output_path = "analysis/grep2"

    grepspec = rdfvalue.GrepSpec(mode=rdfvalue.GrepSpec.Enum("ALL_HITS"),
                                 literal="HIT")

    grepspec.target.path = "/c/Downloads/grepfile.txt"
    grepspec.target.pathtype = rdfvalue.RDFPathSpec.Enum("OS")

    for _ in test_lib.TestFlowHelper(
        "Grep", self.client_mock, client_id=self.client_id,
        request=grepspec, token=self.token, output=output_path):
      pass

    # Check the output file is created
    fd = aff4.FACTORY.Open("aff4:/{0}/{1}".format(self.client_id,
                                                  output_path),
                           token=self.token)
    hits = fd.Get(fd.Schema.HITS)

    self.assertEqual(len(hits), 100)
    self.assertEqual(hits[15].offset, 523)
    self.assertEqual(hits[38], "e. I am a HIT!!random c")
    self.assertEqual(hits[99], "e. I am a HIT!!")

    self.DeleteFile(filename)

  def testPatternAtBufsize(self):
    old_size = searching.Grep.BUFF_SIZE
    try:
      searching.Grep.BUFF_SIZE = 10000

      filename = "/fs/os/c/Downloads/grepfile.txt"
      data = "X" * (searching.Grep.BUFF_SIZE - len("HIT")) + "HIT" + "X" * 1000
      self.CreateFile(filename, data)

      output_path = "analysis/grep"
      output_urn = "aff4:/{0}/{1}".format(self.client_id, output_path)
      data_store.DB.DeleteSubject(output_urn, token=self.token)

      grepspec = rdfvalue.GrepSpec(mode=rdfvalue.GrepSpec.Enum("FIRST_HIT"),
                                   literal="HIT")

      grepspec.target.path = "/c/Downloads/grepfile.txt"
      grepspec.target.pathtype = rdfvalue.RDFPathSpec.Enum("OS")

      for _ in test_lib.TestFlowHelper(
          "Grep", self.client_mock, client_id=self.client_id,
          token=self.token, output=output_path, request=grepspec):
        pass

      # Check the output file is created
      fd = aff4.FACTORY.Open(output_urn, token=self.token)
      hits = fd.Get(fd.Schema.HITS)

      self.assertEqual(len(hits), 1)
      self.assertEqual(hits[0].offset, searching.Grep.BUFF_SIZE - len("HIT"))
      self.assertEqual(hits[0].length, 23)

      self.DeleteFile(filename)
    finally:
      searching.Grep.BUFF_SIZE = old_size

  def testInvalidArg(self):
    """Check that the Grep flow raises if the GrepSpec is invlaid."""
    # No target set.
    grepspec = rdfvalue.GrepSpec(mode=rdfvalue.GrepSpec.Enum("FIRST_HIT"),
                                 literal="hello")

    self.assertRaises(
        type_info.Error, list, test_lib.TestFlowHelper(
            "Grep", self.client_mock, client_id=self.client_id,
            token=self.token, request=grepspec))