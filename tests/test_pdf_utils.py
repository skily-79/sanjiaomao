import doctest
import json
import os
import os.path as osp
import tempfile
import unittest

from ballontranslator.utils import pdf_utils
from ballontranslator.utils.pdf_utils import (
    DEFAULT_PDF_DPI,
    MAX_PDF_DPI,
    MIN_PDF_DPI,
    PdfSupportError,
    clamp_pdf_dpi,
    export_translated_pdf,
    extract_pdf_pages,
    find_pdf_files,
    is_pdf_path,
    is_pdf_project,
    manifest_path,
    pdf_support_available,
    pdf_workdir_for,
    read_pdf_manifest,
    translated_pdf_path,
)

needs_pymupdf = unittest.skipUnless(
    pdf_support_available(), 'PyMuPDF is not installed'
)


def write_manifest(directory: str, manifest) -> None:
    with open(manifest_path(directory), 'w', encoding='utf8') as f:
        json.dump(manifest, f)


class PdfPathHelperTests(unittest.TestCase):

    def test_is_pdf_path_is_case_insensitive(self):
        self.assertTrue(is_pdf_path('/tmp/comic.pdf'))
        self.assertTrue(is_pdf_path('/tmp/comic.PDF'))
        self.assertFalse(is_pdf_path('/tmp/comic.png'))
        self.assertFalse(is_pdf_path(None))

    def test_pdf_workdir_is_sibling_of_source(self):
        workdir = pdf_workdir_for(osp.join('some', 'dir', 'comic.pdf'))
        self.assertEqual(osp.basename(workdir), 'comic_translate')
        self.assertEqual(
            osp.dirname(workdir), osp.dirname(osp.abspath(osp.join('some', 'dir', 'comic.pdf')))
        )

    def test_clamp_dpi_bounds_and_invalid_values(self):
        self.assertEqual(clamp_pdf_dpi(150), 150)
        self.assertEqual(clamp_pdf_dpi(1), MIN_PDF_DPI)
        self.assertEqual(clamp_pdf_dpi(100000), MAX_PDF_DPI)
        # Invalid input must degrade to the default instead of raising, since the
        # value comes from user-editable config.
        self.assertEqual(clamp_pdf_dpi('abc'), DEFAULT_PDF_DPI)
        self.assertEqual(clamp_pdf_dpi(None), DEFAULT_PDF_DPI)

    def test_module_doctests(self):
        results = doctest.testmod(pdf_utils, verbose=False)
        self.assertEqual(results.failed, 0)

    def test_find_pdf_files_in_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            comic_a = osp.join(tmp_dir, 'a.pdf')
            comic_b = osp.join(tmp_dir, 'b.PDF')
            with open(comic_a, 'wb') as f:
                f.write(b'')
            with open(comic_b, 'wb') as f:
                f.write(b'')
            with open(osp.join(tmp_dir, 'notes.txt'), 'w', encoding='utf8') as f:
                f.write('ignore me')

            self.assertEqual(find_pdf_files(tmp_dir), [comic_a, comic_b])
            self.assertEqual(find_pdf_files(comic_a), [comic_a])
            self.assertEqual(find_pdf_files(osp.join(tmp_dir, 'notes.txt')), [])
            self.assertEqual(find_pdf_files('/nonexistent/dir'), [])

    def test_find_pdf_files_recursive_skips_translate_dirs(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            sub = osp.join(tmp_dir, 'sub')
            os.makedirs(sub)
            work = osp.join(tmp_dir, 'comic_translate')
            os.makedirs(work)
            top_pdf = osp.join(tmp_dir, 'a.pdf')
            sub_pdf = osp.join(sub, 'b.pdf')
            gen_pdf = osp.join(work, 'c.pdf')
            for p in (top_pdf, sub_pdf, gen_pdf):
                with open(p, 'wb') as f:
                    f.write(b'')

            result = find_pdf_files(tmp_dir, recursive=True)
            self.assertEqual(result, [top_pdf, sub_pdf])
            # Non-recursive still only sees the top level.
            self.assertEqual(find_pdf_files(tmp_dir), [top_pdf])

    def test_find_pdf_files_recursive_respects_exclude_dirs(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            custom = osp.join(tmp_dir, 'my_output')
            os.makedirs(custom)
            top_pdf = osp.join(tmp_dir, 'a.pdf')
            hidden_pdf = osp.join(custom, 'b.pdf')
            for p in (top_pdf, hidden_pdf):
                with open(p, 'wb') as f:
                    f.write(b'')

            self.assertEqual(
                find_pdf_files(tmp_dir, recursive=True, exclude_dirs={'my_output'}),
                [top_pdf],
            )
            self.assertEqual(
                find_pdf_files(tmp_dir, recursive=True),
                [top_pdf, hidden_pdf],
            )


class PdfManifestTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.addCleanup(self._tmp.cleanup)

    def test_plain_image_dir_is_not_a_pdf_project(self):
        self.assertIsNone(read_pdf_manifest(self.dir))
        self.assertFalse(is_pdf_project(self.dir))
        self.assertIsNone(translated_pdf_path(self.dir))

    def test_malformed_entries_are_discarded_but_rest_loads(self):
        write_manifest(self.dir, {
            'version': 1,
            'source_pdf': osp.join(self.dir, 'comic.pdf'),
            'dpi': 200,
            'pages': [
                {'index': 0, 'image': '0001.png', 'width': 595.0, 'height': 842.0},
                'not-a-dict',
                {'index': 1, 'width': 595.0, 'height': 842.0},          # no image name
                {'index': 2, 'image': '0002.png', 'width': 'x', 'height': None},
            ],
        })

        manifest = read_pdf_manifest(self.dir)
        self.assertEqual([p['image'] for p in manifest['pages']], ['0001.png', '0002.png'])
        # Indexes are re-packed so downstream page ordering stays contiguous.
        self.assertEqual([p['index'] for p in manifest['pages']], [0, 1])
        # Unparsable geometry becomes 0 so export can derive size from the render dpi.
        self.assertEqual((manifest['pages'][1]['width'], manifest['pages'][1]['height']), (0.0, 0.0))
        self.assertEqual(manifest['dpi'], 200)
        self.assertTrue(is_pdf_project(self.dir))

    def test_out_of_range_dpi_in_manifest_is_clamped(self):
        write_manifest(self.dir, {'pages': [{'image': '0001.png'}], 'dpi': 100000})
        self.assertEqual(read_pdf_manifest(self.dir)['dpi'], MAX_PDF_DPI)

    def test_unreadable_manifest_does_not_raise(self):
        with open(manifest_path(self.dir), 'w', encoding='utf8') as f:
            f.write('{ this is not json')
        self.assertIsNone(read_pdf_manifest(self.dir))
        self.assertFalse(is_pdf_project(self.dir))

    def test_non_dict_manifest_does_not_raise(self):
        write_manifest(self.dir, ['unexpected'])
        self.assertIsNone(read_pdf_manifest(self.dir))

    def test_manifest_without_pages_is_not_a_pdf_project(self):
        write_manifest(self.dir, {'version': 1, 'pages': []})
        self.assertFalse(is_pdf_project(self.dir))

    def test_translated_pdf_path_uses_source_stem(self):
        write_manifest(self.dir, {
            'source_pdf': osp.join(self.dir, 'comic.pdf'),
            'pages': [{'image': '0001.png'}],
        })
        self.assertEqual(
            translated_pdf_path(self.dir), osp.join(self.dir, 'comic_translated.pdf')
        )

    def test_translated_pdf_path_falls_back_to_directory_name(self):
        write_manifest(self.dir, {'source_pdf': '', 'pages': [{'image': '0001.png'}]})
        expected = osp.join(self.dir, osp.basename(osp.abspath(self.dir)) + '_translated.pdf')
        self.assertEqual(translated_pdf_path(self.dir), expected)

    def test_export_rejects_non_pdf_project(self):
        with self.assertRaises(PdfSupportError):
            export_translated_pdf(self.dir)


@needs_pymupdf
class PdfRoundTripTests(unittest.TestCase):
    """Extract a generated PDF, then rebuild it from the page renders."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.addCleanup(self._tmp.cleanup)
        self.pdf_path = osp.join(self.dir, 'comic.pdf')
        self.page_size = (595.0, 842.0)
        self.page_count = 3

        import pymupdf  # available: guarded by needs_pymupdf
        doc = pymupdf.open()
        for ii in range(self.page_count):
            page = doc.new_page(width=self.page_size[0], height=self.page_size[1])
            page.insert_text((72, 72), f'page {ii + 1}')
        doc.save(self.pdf_path)
        doc.close()

    def test_extract_writes_pages_and_manifest(self):
        seen = []
        workdir = extract_pdf_pages(
            self.pdf_path, dpi=MIN_PDF_DPI, progress_cb=lambda i, t: seen.append((i, t))
        )

        self.assertEqual(workdir, pdf_workdir_for(self.pdf_path))
        for ii in range(self.page_count):
            self.assertTrue(osp.exists(osp.join(workdir, f'{ii + 1:04d}.png')))
        self.assertEqual(seen, [(i + 1, self.page_count) for i in range(self.page_count)])

        manifest = read_pdf_manifest(workdir)
        self.assertEqual(len(manifest['pages']), self.page_count)
        self.assertEqual(manifest['source_pdf'], osp.abspath(self.pdf_path))
        self.assertEqual(manifest['dpi'], MIN_PDF_DPI)
        self.assertAlmostEqual(manifest['pages'][0]['width'], self.page_size[0], places=1)
        self.assertAlmostEqual(manifest['pages'][0]['height'], self.page_size[1], places=1)

    def test_extract_reuses_existing_renders(self):
        workdir = extract_pdf_pages(self.pdf_path, dpi=MIN_PDF_DPI)
        first_page = osp.join(workdir, '0001.png')
        # Stand in for a user-edited render: reuse must not overwrite it.
        with open(first_page, 'rb') as f:
            original = f.read()
        marker = original + b'\x00edited'
        with open(first_page, 'wb') as f:
            f.write(marker)

        extract_pdf_pages(self.pdf_path, dpi=MIN_PDF_DPI, reuse_existing=True)
        with open(first_page, 'rb') as f:
            self.assertEqual(f.read(), marker)

        extract_pdf_pages(self.pdf_path, dpi=MIN_PDF_DPI, reuse_existing=False)
        with open(first_page, 'rb') as f:
            self.assertNotEqual(f.read(), marker)

    def test_export_keeps_page_geometry_and_reports_missing_pages(self):
        workdir = extract_pdf_pages(self.pdf_path, dpi=MIN_PDF_DPI)
        result_dir = osp.join(workdir, 'result')
        os.makedirs(result_dir, exist_ok=True)
        # Only the first page has been rendered by the pipeline.
        import shutil
        shutil.copyfile(osp.join(workdir, '0001.png'), osp.join(result_dir, '0001.png'))

        save_path, missing = export_translated_pdf(workdir, result_dir)

        self.assertEqual(save_path, osp.join(self.dir, 'comic_translated.pdf'))
        self.assertTrue(osp.exists(save_path))
        # Unrendered pages fall back to the source render and are reported.
        self.assertEqual(missing, ['0002.png', '0003.png'])

        import pymupdf
        out = pymupdf.open(save_path)
        try:
            self.assertEqual(out.page_count, self.page_count)
            rect = out.load_page(0).rect
            self.assertAlmostEqual(rect.width, self.page_size[0], places=0)
            self.assertAlmostEqual(rect.height, self.page_size[1], places=0)
        finally:
            out.close()

    def test_export_derives_geometry_when_manifest_lacks_size(self):
        workdir = extract_pdf_pages(self.pdf_path, dpi=MIN_PDF_DPI)
        manifest = read_pdf_manifest(workdir)
        for page in manifest['pages']:
            page['width'] = page['height'] = 0
        write_manifest(workdir, manifest)

        save_path, _ = export_translated_pdf(
            workdir, save_path=osp.join(self.dir, 'derived.pdf')
        )

        import pymupdf
        out = pymupdf.open(save_path)
        try:
            rect = out.load_page(0).rect
            # Derived from the render dpi, so it should match the original points.
            self.assertAlmostEqual(rect.width, self.page_size[0], delta=2)
            self.assertAlmostEqual(rect.height, self.page_size[1], delta=2)
        finally:
            out.close()

    def test_extract_missing_file_raises(self):
        with self.assertRaises(PdfSupportError):
            extract_pdf_pages(osp.join(self.dir, 'nope.pdf'))


if __name__ == '__main__':
    unittest.main()
