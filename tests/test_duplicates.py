import unittest
from bridge.duplicates import find_duplicates, normalize_phone, validate_removals


def contact(key,name,number):return {'id':key,'name':name,'detail':number}


class DuplicateReviewTests(unittest.TestCase):
    def test_shared_full_number_matches_formats(self):
        rows=[contact('1','Alice','+256 700-123-456'),contact('2','Another name','00256 (700) 123456')]
        groups=find_duplicates(rows)
        self.assertEqual(len(groups),1)
        self.assertEqual(groups[0]['reason'],'Shared phone number')

    def test_no_short_suffix_or_country_code_guessing(self):
        rows=[contact('1','Alice','+256700123456'),contact('2','Bob','0700123456'),contact('3','Carol','+44700123456')]
        self.assertFalse(find_duplicates(rows))
        self.assertEqual(normalize_phone('123'),'')

    def test_name_match_is_flagged_separately(self):
        groups=find_duplicates([contact('1',' Alice  Example ','123456789'),contact('2','alice example','987654321')])
        self.assertEqual(len(groups),1)
        self.assertIn('review carefully',groups[0]['reason'])

    def test_overlapping_groups_keep_at_least_one_record(self):
        groups=find_duplicates([contact('1','Alice','123456789'),contact('2','Alice','123456789')])
        self.assertEqual(validate_removals(groups,{'2'}),{'2'})
        with self.assertRaises(ValueError):validate_removals(groups,{'1','2'})

    def test_unknown_names_and_repeated_number_on_one_contact_not_duplicates(self):
        self.assertFalse(find_duplicates([contact('1','Unnamed contact','123456789 · 123456789'),contact('2','Unnamed contact','987654321')]))
