#
# This source file is part of the EdgeDB open source project.
#
# Copyright 2017-present MagicStack Inc. and the EdgeDB authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


import os.path

import edgedb

from edb.testbase import server as tb
from edb.tools import test


class TestEdgeQLPolicies(tb.QueryTestCase):
    '''Tests for policies.'''

    SCHEMA = os.path.join(os.path.dirname(__file__), 'schemas',
                          'issues.esdl')

    SETUP = [
        os.path.join(os.path.dirname(__file__), 'schemas',
                     'issues_setup.edgeql'),
        '''
            # These are for testing purposes and don't really model anything
            create required global cur_owner_active -> bool {
                set default := true;
            };
            create required global watchers_active -> bool {
                set default := true;
            };

            create required global filter_owned -> bool {
                set default := false;
            };
            create global cur_user -> str;

            alter type Owned {
                create access policy disable_filter
                  when (not global filter_owned)
                  allow read using (true);

                create access policy cur_owner
                  when (global cur_owner_active)
                  allow read using (.owner.name ?= global cur_user);
            };

            alter type Issue {
                create access policy cur_watchers
                  when (global watchers_active)
                  allow read using (
                      (global cur_user IN __subject__.watchers.name) ?? false
                  )
            };
        '''
    ]

    async def test_edgeql_policies_01(self):
        await self.con.execute('''
            set global cur_owner_active := false;
        ''')
        await self.con.execute('''
            set global watchers_active := false;
        ''')
        await self.con.execute('''
            set global filter_owned := True;
        ''')

        await self.assert_query_result(
            r'''
                select Owned { [IS Named].name }
            ''',
            []
        )

        await self.assert_query_result(
            r'''
                select Issue { name }
            ''',
            []
        )

    async def test_edgeql_policies_02(self):
        await self.con.execute('''
            set global cur_user := 'Yury';
        ''')
        await self.con.execute('''
            set global filter_owned := True;
        ''')

        await self.assert_query_result(
            r'''
                select Owned { [IS Named].name }
            ''',
            tb.bag([
                {"name": "Release EdgeDB"},
                {"name": "Improve EdgeDB repl output rendering."},
                {"name": "Repl tweak."},
            ])
        )

        await self.assert_query_result(
            r'''
                select Issue { name }
            ''',
            tb.bag([
                {"name": "Release EdgeDB"},
                {"name": "Improve EdgeDB repl output rendering."},
                {"name": "Repl tweak."},
            ])
        )

    async def test_edgeql_policies_03(self):
        vals = await self.con.query('''
            select Object.id
        ''')
        self.assertEqual(len(vals), len(set(vals)))

    async def test_edgeql_policies_04(self):
        await self.con.execute('''
            set global cur_user := 'Phil';
        ''')
        await self.con.execute('''
            set global filter_owned := True;
        ''')

        await self.assert_query_result(
            r'''
                select URL { src := .<references[IS User] }
            ''',
            tb.bag([
                {"src": []}
            ])
        )

        await self.assert_query_result(
            r'''
                select URL { src := .<references }
            ''',
            tb.bag([
                {"src": []}
            ])
        )

    async def test_edgeql_policies_05(self):
        await self.con.execute('''
            CREATE TYPE Tgt {
                CREATE REQUIRED PROPERTY b -> bool;

                CREATE ACCESS POLICY redact
                    ALLOW READ USING (not global filter_owned);
                CREATE ACCESS POLICY dml_always
                    ALLOW WRITE DELETE USING (true);
            };
            CREATE TYPE Ptr {
                CREATE REQUIRED LINK tgt -> Tgt;
            };
        ''')
        await self.con.query('''
            insert Ptr { tgt := (insert Tgt { b := True }) };
        ''')
        await self.con.execute('''
            set global filter_owned := True;
        ''')

        async with self.assertRaisesRegexTx(
                edgedb.CardinalityViolationError,
                r"returned an empty set"):
            await self.con.query('''
                select Ptr { tgt }
            ''')

        async with self.assertRaisesRegexTx(
                edgedb.CardinalityViolationError,
                r"returned an empty set"):
            await self.con.query('''
                select Ptr { z := .tgt.b }
            ''')

        async with self.assertRaisesRegexTx(
                edgedb.CardinalityViolationError,
                r"returned an empty set"):
            await self.con.query('''
                select Ptr.tgt
            ''')

        async with self.assertRaisesRegexTx(
                edgedb.CardinalityViolationError,
                r"returned an empty set"):
            await self.con.query('''
                select Ptr.tgt.b
            ''')

        await self.con.query('''
            delete Ptr
        ''')

        await self.assert_query_result(
            r''' select Ptr { tgt }''',
            [],
        )

        await self.assert_query_result(
            r''' select Ptr.tgt''',
            [],
        )

        await self.assert_query_result(
            r''' select Ptr.tgt.b''',
            [],
        )

    async def test_edgeql_policies_06(self):
        await self.con.execute('''
            CREATE TYPE Tgt {
                CREATE REQUIRED PROPERTY b -> bool;

                CREATE ACCESS POLICY redact
                    ALLOW READ USING (not global filter_owned);
                CREATE ACCESS POLICY dml_always
                    ALLOW WRITE DELETE USING (true);
            };
            CREATE TYPE BadTgt;
            CREATE TYPE Ptr {
                CREATE REQUIRED LINK tgt -> Tgt | BadTgt;
            };
        ''')
        await self.con.query('''
            insert Ptr { tgt := (insert Tgt { b := True }) };
        ''')
        await self.con.execute('''
            set global filter_owned := True;
        ''')

        async with self.assertRaisesRegexTx(
                edgedb.CardinalityViolationError,
                r"returned an empty set"):
            await self.con.query('''
                select Ptr { tgt }
            ''')
