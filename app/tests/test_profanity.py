import unittest

from app.services.profanity import contains_profanity, mask_profanity, normalize


class ProfanityNormalizationTests(unittest.TestCase):
    def test_invisible_and_compatibility_forms_are_unfolded(self):
        for text in ('씨​발', '씨﻿발', 'ＦＵＣＫ', 'Ⓢhit'):
            self.assertTrue(contains_profanity(text), repr(text))

    def test_masking_positions_stay_correct_after_normalizing(self):
        # 원문에서 치환하면 제거된 제로폭 문자만큼 위치가 밀린다.
        masked, found = mask_profanity('씨​발 이게 뭐야')
        self.assertTrue(found)
        self.assertEqual(masked, '■■ 이게 뭐야')

    def test_ordinary_sentences_are_unchanged_by_normalizing(self):
        for text in ('오늘 시발점이 어디야', '제 생년월일은 1995년이에요',
                     '사업이 시작됐어', '개나리가 폈어'):
            self.assertEqual(normalize(text), text)
            self.assertFalse(contains_profanity(text), text)


if __name__ == '__main__':
    unittest.main()
