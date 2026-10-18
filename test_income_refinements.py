"""Synthetic regressions for categories, private payer policy and Intesa status."""
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from openpyxl import Workbook
import app
from src.portfolio_dashboard.movements.personal import PersonalLedger


class IncomeRefinements(unittest.TestCase):
    def test_custom_categories_are_persistent_and_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = PersonalLedger(Path(directory) / 'ledger.sqlite3')
            ledger.add_category('one', '  Learning   materials ')
            self.assertIn('Learning materials', ledger.categories('one', {'Income'}))
            self.assertNotIn('Learning materials', ledger.categories('two', {'Income'}))
            with self.assertRaises(ValueError):
                ledger.add_category('one', ' ')

    def test_policy_is_opt_in_and_matches_transfer_payer_only(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = PersonalLedger(Path(directory) / 'ledger.sqlite3')
            ledger.set_credit_payers('one', ['Example Parent'])
            def event(i, kind, description):
                return dict(movement_id=i, source='bank', merchant='Bank', description=description,
                            flow_kind=kind, category='Credits', subcategory='')
            rows = ledger.classify('one', [event(1,'credit','Cashback'), event(2,'income','Bonifico EXAMPLE PARENT'),
                                          event(3,'income','Bonifico Example Parentless'), event(4,'income','Salary Example Parent'),
                                          event(5,'spend','Bonifico Example Parent')])
            self.assertEqual([r['flow_kind'] for r in rows], ['income','credit','income','income','spend'])
            self.assertEqual(ledger.classify('two', [event(6,'credit','Cashback')])[0]['flow_kind'],'credit')

    def test_native_intesa_booked_statuses(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'native.xlsx'
            wb = Workbook(); ws = wb.active; ws.title = 'Lista Operazione'
            ws.append(['Data','Operazione','Dettagli','Contabilizzazione','Categoria ','Valuta','Importo'])
            for status in ['CONTABILIZZATO','CONTABILIZZATA','NON CONTABILIZZATO']:
                ws.append([datetime(2026,10,1),'Salary','Payroll',status,'Stipendi','EUR',100])
            wb.save(path)
            rows = app.read_intesa_expense_events(path, rules=[])
            self.assertEqual(len(rows),2)
            self.assertEqual({r['flow_kind'] for r in rows},{'income'})

if __name__ == '__main__':
    unittest.main()
