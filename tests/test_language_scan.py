from datetime import datetime,timezone
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('scan',Path(__file__).resolve().parents[1]/'scripts/scan_languages.py')
scan=importlib.util.module_from_spec(spec);spec.loader.exec_module(scan)


class LanguageScanTests(unittest.TestCase):
    def test_nested_roots_are_counted_once(self):
        with tempfile.TemporaryDirectory() as value:
            root=Path(value); child=root/'child';child.mkdir()
            self.assertEqual(scan.unique_roots([root,child,root]),[root.resolve()])

    def test_only_aggregate_counts_and_aliases_are_exported(self):
        row={'Name':'TypeScript','Bytes':100,'Count':1,'Code':8,'Files':[{'Location':'private-project/secret.ts'}]}
        other={**row,'Name':'TSX','Bytes':200,'Files':['private-source']}
        empty={**row,'Name':'C Header','Code':0}
        result=scan.sanitize([row,other,empty],2,datetime.now(timezone.utc),False)
        self.assertNotIn('private',json.dumps(result))
        self.assertEqual(result['languages'],[{'name':'TypeScript','bytes':300,'files':2,'code_lines':16}])

    def test_invalid_counts_are_rejected(self):
        with self.assertRaises(ValueError):
            scan.sanitize([{'Name':'Python','Bytes':-1,'Count':1,'Code':2}],1,datetime.now(timezone.utc),False)
