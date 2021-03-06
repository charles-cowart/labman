# ----------------------------------------------------------------------------
# Copyright (c) 2017-, LabControl development team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file LICENSE, distributed with this software.
# ----------------------------------------------------------------------------

from unittest import main
from re import escape, search
import pandas
import hashlib

import numpy as np
import numpy.testing as npt
import pandas as pd
import os.path
from datetime import datetime

from labcontrol.db import sql_connection
from labcontrol.db.testing import LabControlTestCase
from labcontrol.db.container import Tube, Well
from labcontrol.db.composition import (
    ReagentComposition, SampleComposition, GDNAComposition,
    LibraryPrep16SComposition, Composition, PoolComposition,
    PrimerSetComposition, LibraryPrepShotgunComposition, PrimerSet)
from labcontrol.db.user import User
from labcontrol.db.plate import Plate, PlateConfiguration
from labcontrol.db.equipment import Equipment
from labcontrol.db.process import (
    Process, SamplePlatingProcess, ReagentCreationProcess,
    PrimerWorkingPlateCreationProcess, GDNAExtractionProcess,
    LibraryPrep16SProcess, QuantificationProcess, PoolingProcess,
    SequencingProcess, GDNAPlateCompressionProcess, NormalizationProcess,
    LibraryPrepShotgunProcess)
from labcontrol.db.sheet import Sheet, SampleSheet, SampleSheet16S, SampleSheetShotgun


def load_data(filename):
    "Helper function to read files in the tests/data folder"
    path = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(path, 'data', filename)
    with open(path) as f:
        return f.read()


NORM_PROCESS_PICKLIST = load_data('norm-process-picklist.txt')
NORM_PROCESS_PICKLIST_SID = load_data('norm-process-picklist-specimen-id.txt')
COMBINED_SAMPLES_AMPLICON_PREP_EXAMPLE = load_data(
    'experimental-plus-samples-amplicon-prep-example.txt')
COMBINED_SAMPLES_METAGENOMICS_PREP_EXAMPLE = load_data(
    'experimental-plus-samples-metagenomics-prep-example.txt')
SHOTGUN_SAMPLE_SHEET = load_data("shotgun_sample_sheet.txt")
POOLING_PROCESS_ECHO_PICKLIST = load_data("pooling-process-echo-picklist.txt")
LOW_MAX_VOL_POOLING_PROCESS_ECHO_PICKLIST = load_data(
    "low-max-vol-pooling-process-echo-picklist.txt")


def _help_compare_timestamps(input_datetime):
    # can't really check that the timestamp is an exact value,
    # so instead check that current time (having just created process)
    # is within 60 seconds of time at which process was created.
    # This is a heuristic--may fail if you e.g. put a breakpoint
    # between create call and assertLess call.
    time_diff = datetime.now() - input_datetime
    is_close = time_diff.total_seconds() < 60
    return is_close


def _help_make_datetime(input_datetime_str):
    # input_datetime_str should be in format '2017-10-25 19:10:25'
    return datetime.strptime(input_datetime_str, '%Y-%m-%d %H:%M:%S')


class TestProcess(LabControlTestCase):
    def test_factory(self):
        self.assertEqual(Process.factory(11),
                         SamplePlatingProcess(11))
        self.assertEqual(Process.factory(6),
                         ReagentCreationProcess(6))
        self.assertEqual(Process.factory(4),
                         PrimerWorkingPlateCreationProcess(1))
        self.assertEqual(Process.factory(12),
                         GDNAExtractionProcess(1))
        self.assertEqual(Process.factory(19),
                         GDNAPlateCompressionProcess(1))
        self.assertEqual(Process.factory(13),
                         LibraryPrep16SProcess(1))
        self.assertEqual(Process.factory(21),
                         NormalizationProcess(1))
        self.assertEqual(Process.factory(22),
                         LibraryPrepShotgunProcess(1))
        self.assertEqual(Process.factory(14),
                         QuantificationProcess(1))
        self.assertEqual(Process.factory(15),
                         QuantificationProcess(2))
        self.assertEqual(Process.factory(16), PoolingProcess(1))
        self.assertEqual(Process.factory(18), SequencingProcess(1))


class TestSamplePlatingProcess(LabControlTestCase):
    def test_attributes(self):
        tester = SamplePlatingProcess(11)
        self.assertEqual(tester.date,
                         _help_make_datetime('2017-10-25 19:10:25'))
        self.assertEqual(tester.personnel, User('test@foo.bar'))
        self.assertEqual(tester.process_id, 11)
        self.assertEqual(tester.plate, Plate(21))

    def test_create(self):
        user = User('test@foo.bar')
        # 1 -> 96-well deep-well plate
        plate_config = PlateConfiguration(1)
        obs = SamplePlatingProcess.create(
            user, plate_config, 'unittest Plate 1', 10)

        self.assertTrue(_help_compare_timestamps(obs.date))
        self.assertEqual(obs.personnel, user)

        # Check that the plate has been created with the correct values
        obs_plate = obs.plate
        self.assertIsInstance(obs_plate, Plate)
        self.assertEqual(obs_plate.external_id, 'unittest Plate 1')
        self.assertEqual(obs_plate.plate_configuration, plate_config)
        self.assertFalse(obs_plate.discarded)
        self.assertIsNone(obs_plate.notes)

        # Check that all the wells in the plate contain blanks
        plate_layout = obs_plate.layout
        for i, row in enumerate(plate_layout):
            for j, well in enumerate(row):
                self.assertIsInstance(well, Well)
                self.assertEqual(well.plate, obs_plate)
                self.assertEqual(well.row, i + 1)
                self.assertEqual(well.column, j + 1)
                self.assertEqual(well.latest_process, obs)
                obs_composition = well.composition
                self.assertIsInstance(obs_composition, SampleComposition)
                self.assertEqual(obs_composition.sample_composition_type,
                                 'blank')
                self.assertIsNone(obs_composition.sample_id)
                self.assertEqual(obs_composition.content,
                                 'blank.%s.%s' % ("unittest.Plate.1",
                                                  well.well_id))
                self.assertEqual(obs_composition.upstream_process, obs)
                self.assertEqual(obs_composition.container, well)
                self.assertEqual(obs_composition.total_volume, 10)

    def test_update_well(self):
        tester = SamplePlatingProcess(11)
        obs = SampleComposition(8)

        self.assertEqual(obs.sample_composition_type, 'blank')
        self.assertIsNone(obs.sample_id)
        self.assertEqual(obs.content, 'blank.Test.plate.1.H1')

        # Update a well from CONTROL -> EXPERIMENTAL SAMPLE
        self.assertEqual(
            tester.update_well(8, 1, '1.SKM8.640201'), ('1.SKM8.640201', True))
        self.assertEqual(obs.sample_composition_type, 'experimental sample')
        self.assertEqual(obs.sample_id, '1.SKM8.640201')
        self.assertEqual(obs.content, '1.SKM8.640201')

        # Update a well from EXPERIMENTAL SAMPLE -> EXPERIMENTAL SAMPLE
        self.assertEqual(
            tester.update_well(8, 1, '1.SKB6.640176'),
            ('1.SKB6.640176.Test.plate.1.H1', True))
        self.assertEqual(obs.sample_composition_type, 'experimental sample')
        self.assertEqual(obs.sample_id, '1.SKB6.640176')
        self.assertEqual(obs.content, '1.SKB6.640176.Test.plate.1.H1')

        # Update a well from EXPERIMENTAL SAMPLE -> CONTROL
        self.assertEqual(tester.update_well(8, 1, 'vibrio.positive.control'),
                         ('vibrio.positive.control.Test.plate.1.H1', True))
        self.assertEqual(obs.sample_composition_type,
                         'vibrio.positive.control')
        self.assertIsNone(obs.sample_id)
        self.assertEqual(obs.content,
                         'vibrio.positive.control.Test.plate.1.H1')

        # Update a well from CONTROL -> CONTROL
        self.assertEqual(tester.update_well(8, 1, 'blank'),
                         ('blank.Test.plate.1.H1', True))
        self.assertEqual(obs.sample_composition_type, 'blank')
        self.assertIsNone(obs.sample_id)
        self.assertEqual(obs.content, 'blank.Test.plate.1.H1')

    def test_comment_well(self):
        tester = SamplePlatingProcess(11)
        obs = SampleComposition(8)

        self.assertIsNone(obs.notes)
        tester.comment_well(8, 1, 'New notes')
        self.assertEqual(obs.notes, 'New notes')
        tester.comment_well(8, 1, None)
        self.assertIsNone(obs.notes)

    def test_notes(self):
        tester = SamplePlatingProcess(11)

        self.assertIsNone(tester.notes)
        tester.notes = 'This note was set in a test'
        self.assertEqual(tester.notes, 'This note was set in a test')


class TestReagentCreationProcess(LabControlTestCase):
    def test_attributes(self):
        tester = ReagentCreationProcess(6)
        self.assertEqual(tester.date,
                         _help_make_datetime('2017-10-23 09:10:25'))
        self.assertEqual(tester.personnel, User('test@foo.bar'))
        self.assertEqual(tester.process_id, 6)
        self.assertEqual(tester.tube, Tube(2))

    def test_create(self):
        user = User('test@foo.bar')
        obs = ReagentCreationProcess.create(user, 'Reagent external id', 10,
                                            'extraction kit')
        self.assertTrue(_help_compare_timestamps(obs.date))
        self.assertEqual(obs.personnel, user)

        # Check that the tube has been create with the correct values
        obs_tube = obs.tube
        self.assertIsInstance(obs_tube, Tube)
        self.assertEqual(obs_tube.external_id, 'Reagent external id')
        self.assertEqual(obs_tube.remaining_volume, 10)
        self.assertIsNone(obs_tube.notes)
        self.assertEqual(obs_tube.latest_process, obs)

        # Perform the reagent composition checks
        obs_composition = obs_tube.composition
        self.assertIsInstance(obs_composition, ReagentComposition)
        self.assertEqual(obs_composition.container, obs_tube)
        self.assertEqual(obs_composition.total_volume, 10)
        self.assertIsNone(obs_composition.notes)
        self.assertEqual(obs_composition.external_lot_id,
                         'Reagent external id')
        self.assertEqual(obs_composition.reagent_type, 'extraction kit')


class TestPrimerWorkingPlateCreationProcess(LabControlTestCase):
    def test_attributes(self):
        tester = PrimerWorkingPlateCreationProcess(1)
        self.assertEqual(tester.date,
                         _help_make_datetime('2017-10-23 19:10:25'))
        self.assertEqual(tester.personnel, User('test@foo.bar'))
        self.assertEqual(tester.process_id, 4)
        exp_plates = [Plate(11), Plate(12), Plate(13), Plate(14),
                      Plate(15), Plate(16), Plate(17), Plate(18)]
        self.assertEqual(tester.primer_set, PrimerSet(1))
        self.assertEqual(tester.master_set_order, 'EMP PRIMERS MSON 1')
        self.assertEqual(tester.plates, exp_plates)

    def test_create(self):
        test_date = _help_make_datetime('2018-01-18 00:00:00')
        user = User('test@foo.bar')
        primer_set = PrimerSet(1)
        obs = PrimerWorkingPlateCreationProcess.create(
            user, primer_set, 'Master Set Order 1',
            creation_date=test_date)
        self.assertEqual(obs.date, test_date)
        self.assertEqual(obs.personnel, user)
        self.assertEqual(obs.primer_set, primer_set)
        self.assertEqual(obs.master_set_order, 'Master Set Order 1')

        obs_plates = obs.plates
        obs_date = datetime.strftime(obs.date, Process.get_date_format())
        self.assertEqual(len(obs_plates), 8)
        self.assertEqual(obs_plates[0].external_id,
                         'EMP 16S V4 primer plate 1 ' + obs_date)
        self.assertEqual(
            obs_plates[0].get_well(1, 1).composition.primer_set_composition,
            PrimerSetComposition(1))

        # This tests the edge case in which a plate already exists that has
        # the external id that would usually be generated by the create
        # process, in which case a 4-digit random number is added as a
        # disambiguator.
        obs = PrimerWorkingPlateCreationProcess.create(
            user, primer_set, 'Master Set Order 1',
            creation_date=str(obs.date))
        obs_ext_id = obs.plates[0].external_id
        regex = r'EMP 16S V4 primer plate 1 ' + escape(obs_date) + \
                ' \d\d\d\d$'
        matches = search(regex, obs_ext_id)
        self.assertIsNotNone(matches)


class TestGDNAExtractionProcess(LabControlTestCase):
    def test_attributes(self):
        tester = GDNAExtractionProcess(1)

        self.assertEqual(tester.date,
                         _help_make_datetime('2017-10-25 19:10:25'))
        self.assertEqual(tester.personnel, User('test@foo.bar'))
        self.assertEqual(tester.process_id, 12)
        self.assertEqual(tester.kingfisher, Equipment(11))
        self.assertEqual(tester.epmotion, Equipment(5))
        self.assertEqual(tester.epmotion_tool, Equipment(15))
        self.assertEqual(tester.extraction_kit, ReagentComposition(2))
        self.assertEqual(tester.sample_plate.id, 21)
        self.assertEqual(tester.volume, 10)
        self.assertIsNone(tester.notes)

    def test_create(self):
        test_date = _help_make_datetime('2018-01-01 00:00:01')
        user = User('test@foo.bar')
        ep_robot = Equipment(6)
        kf_robot = Equipment(11)
        tool = Equipment(15)
        kit = ReagentComposition(1)
        plate = Plate(21)
        notes = 'test note'
        obs = GDNAExtractionProcess.create(
            user, plate, kf_robot, ep_robot, tool, kit, 10,
            'gdna - Test plate 1',
            extraction_date=test_date, notes=notes)
        self.assertEqual(obs.date, test_date)
        self.assertEqual(obs.personnel, user)
        self.assertEqual(obs.kingfisher, Equipment(11))
        self.assertEqual(obs.epmotion, Equipment(6))
        self.assertEqual(obs.epmotion_tool, Equipment(15))
        self.assertEqual(obs.extraction_kit, ReagentComposition(1))
        self.assertEqual(obs.sample_plate, Plate(21))
        self.assertEqual(obs.volume, 10)
        self.assertEqual(obs.notes, 'test note')

        # Check the extracted plate
        obs_plates = obs.plates
        self.assertEqual(len(obs_plates), 1)
        obs_plate = obs_plates[0]
        self.assertIsInstance(obs_plate, Plate)
        self.assertEqual(obs_plate.external_id, 'gdna - Test plate 1')
        self.assertEqual(obs_plate.plate_configuration,
                         plate.plate_configuration)
        self.assertFalse(obs_plate.discarded)

        # Check the wells in the plate
        plate_layout = obs_plate.layout
        for i, row in enumerate(plate_layout):
            for j, well in enumerate(row):
                if i == 7 and j == 11:
                    # The last well of the plate is an empty well
                    self.assertIsNone(well)
                else:
                    self.assertIsInstance(well, Well)
                    self.assertEqual(well.plate, obs_plate)
                    self.assertEqual(well.row, i + 1)
                    self.assertEqual(well.column, j + 1)
                    self.assertEqual(well.latest_process, obs)
                    obs_composition = well.composition
                    self.assertIsInstance(obs_composition, GDNAComposition)
                    self.assertEqual(obs_composition.upstream_process, obs)
                    self.assertEqual(obs_composition.container, well)
                    self.assertEqual(obs_composition.total_volume, 10)

        # The sample compositions of the gDNA compositions change depending on
        # the well. Spot check a few sample and controls
        self.assertEqual(
            plate_layout[0][0].composition.sample_composition.sample_id,
            '1.SKB1.640202')
        self.assertEqual(
            plate_layout[1][1].composition.sample_composition.sample_id,
            '1.SKB2.640194')
        self.assertIsNone(
            plate_layout[6][0].composition.sample_composition.sample_id)
        self.assertEqual(
            plate_layout[
                6][0].composition.sample_composition.sample_composition_type,
            'vibrio.positive.control')
        self.assertIsNone(
            plate_layout[7][0].composition.sample_composition.sample_id)
        self.assertEqual(
            plate_layout[
                7][0].composition.sample_composition.sample_composition_type,
            'blank')


class TestGDNAPlateCompressionProcess(LabControlTestCase):
    def test_get_interleaved_quarters_position_generator(self):
        # ensure error thrown for invalid number of quarters
        exp_err = "Expected number of quarters to be an integer between 1 " \
                  "and 4 but received 5"
        with self.assertRaisesRegex(ValueError, exp_err):
            x = GDNAPlateCompressionProcess\
                .get_interleaved_quarters_position_generator(5, 2, 2)
            next(x)

        exp_err = "Expected number of quarters to be an integer between 1 " \
                  "and 4 but received 1.5"
        with self.assertRaisesRegex(ValueError, exp_err):
            x = GDNAPlateCompressionProcess\
                .get_interleaved_quarters_position_generator(1.5, 2, 2)
            next(x)

        # ensure error thrown for invalid total rows, cols
        exp_err = "Expected number of rows and columns to be positive " \
                  "integers evenly divisible by two but received 0 rows and " \
                  "2 columns"
        with self.assertRaisesRegex(ValueError, exp_err):
            x = GDNAPlateCompressionProcess \
                .get_interleaved_quarters_position_generator(4, 0, 2)
            next(x)

        exp_err = "Expected number of rows and columns to be positive " \
                  "integers evenly divisible by two but received 2 rows and " \
                  "1 columns"
        with self.assertRaisesRegex(ValueError, exp_err):
            x = GDNAPlateCompressionProcess \
                .get_interleaved_quarters_position_generator(4, 2, 1)
            next(x)

        # ensure correct results returned for all numbers of quarters
        x = GDNAPlateCompressionProcess \
            .get_interleaved_quarters_position_generator(1, 16, 24)
        self.assertListEqual(list(x), INTERLEAVED_POSITIONS[:96])

        x = GDNAPlateCompressionProcess \
            .get_interleaved_quarters_position_generator(2, 16, 24)
        self.assertListEqual(list(x), INTERLEAVED_POSITIONS[:192])

        x = GDNAPlateCompressionProcess \
            .get_interleaved_quarters_position_generator(3, 16, 24)
        self.assertListEqual(list(x), INTERLEAVED_POSITIONS[:288])

        x = GDNAPlateCompressionProcess \
            .get_interleaved_quarters_position_generator(4, 16, 24)
        self.assertListEqual(list(x), INTERLEAVED_POSITIONS)

    def test_attributes(self):
        tester = GDNAPlateCompressionProcess(1)
        self.assertEqual(tester.date,
                         _help_make_datetime('2017-10-25 19:10:25'))
        self.assertEqual(tester.personnel, User('test@foo.bar'))
        self.assertEqual(tester.process_id, 19)
        self.assertEqual(tester.plates, [Plate(24)])
        self.assertEqual(tester.robot, Equipment(1))
        self.assertEqual(tester.gdna_plates, [Plate(22), Plate(28), Plate(31),
                                              Plate(34)])

    def test_create(self):
        user = User('test@foo.bar')

        # Create a couple of new plates so it is easy to test the interleaving
        spp = SamplePlatingProcess.create(
            user, PlateConfiguration(1), 'Compression Test 1', 1)
        spp.update_well(1, 1, '1.SKM7.640188')
        spp.update_well(1, 2, '1.SKD9.640182')
        spp.update_well(1, 3, '1.SKM8.640201')
        spp.update_well(1, 4, '1.SKB8.640193')
        spp.update_well(1, 5, '1.SKD2.640178')
        spp.update_well(1, 6, '1.SKM3.640197')
        spp.update_well(1, 7, '1.SKM4.640180')
        spp.update_well(1, 8, '1.SKB9.640200')
        spp.update_well(2, 1, '1.SKB4.640189')
        spp.update_well(2, 2, '1.SKB5.640181')
        spp.update_well(2, 3, '1.SKB6.640176')
        spp.update_well(2, 4, '1.SKM2.640199')
        spp.update_well(2, 5, '1.SKM5.640177')
        spp.update_well(2, 6, '1.SKB1.640202')
        spp.update_well(2, 7, '1.SKD8.640184')
        spp.update_well(2, 8, '1.SKD4.640185')
        plateA = spp.plates[0]

        spp = SamplePlatingProcess.create(
            user, PlateConfiguration(1), 'Compression Test 2', 1)
        spp.update_well(1, 1, '1.SKB4.640189')
        spp.update_well(1, 2, '1.SKB5.640181')
        spp.update_well(1, 3, '1.SKB6.640176')
        spp.update_well(1, 4, '1.SKM2.640199')
        spp.update_well(1, 5, '1.SKM5.640177')
        spp.update_well(1, 6, '1.SKB1.640202')
        spp.update_well(1, 7, '1.SKD8.640184')
        spp.update_well(1, 8, '1.SKD4.640185')
        spp.update_well(2, 1, '1.SKB3.640195')
        spp.update_well(2, 2, '1.SKM1.640183')
        spp.update_well(2, 3, '1.SKB7.640196')
        spp.update_well(2, 4, '1.SKD3.640198')
        spp.update_well(2, 5, '1.SKD7.640191')
        spp.update_well(2, 6, '1.SKD6.640190')
        spp.update_well(2, 7, '1.SKB2.640194')
        spp.update_well(2, 8, '1.SKM9.640192')
        plateB = spp.plates[0]

        # Extract the plates
        ep_robot = Equipment(6)
        tool = Equipment(15)
        kit = ReagentComposition(1)
        ep1 = GDNAExtractionProcess.create(
            user, plateA, Equipment(11), ep_robot, tool, kit, 100,
            'gdna - Test Comp 1')
        ep2 = GDNAExtractionProcess.create(
            user, plateB, Equipment(12), ep_robot, tool, kit, 100,
            'gdna - Test Comp 2')

        obs = GDNAPlateCompressionProcess.create(
            user, [ep1.plates[0], ep2.plates[0]], 'Compressed plate AB',
            Equipment(1))
        self.assertTrue(_help_compare_timestamps(obs.date))
        self.assertEqual(obs.personnel, user)
        obs_plates = obs.plates
        self.assertEqual(len(obs_plates), 1)
        obs_layout = obs_plates[0].layout
        exp_positions = [
            # Row 1 plate A
            (1, 1, '1.SKM7.640188'), (1, 3, '1.SKD9.640182'),
            (1, 5, '1.SKM8.640201'), (1, 7, '1.SKB8.640193'),
            (1, 9, '1.SKD2.640178'), (1, 11, '1.SKM3.640197'),
            (1, 13, '1.SKM4.640180'), (1, 15, '1.SKB9.640200'),
            # Row 1 plate B
            (1, 2, '1.SKB4.640189'), (1, 4, '1.SKB5.640181'),
            (1, 6, '1.SKB6.640176'), (1, 8, '1.SKM2.640199'),
            (1, 10, '1.SKM5.640177'), (1, 12, '1.SKB1.640202'),
            (1, 14, '1.SKD8.640184'), (1, 16, '1.SKD4.640185'),
            # Row 2 plate A
            (3, 1, '1.SKB4.640189'), (3, 3, '1.SKB5.640181'),
            (3, 5, '1.SKB6.640176'), (3, 7, '1.SKM2.640199'),
            (3, 9, '1.SKM5.640177'), (3, 11, '1.SKB1.640202'),
            (3, 13, '1.SKD8.640184'), (3, 15, '1.SKD4.640185'),
            # Row 2 plate B
            (3, 2, '1.SKB3.640195'), (3, 4, '1.SKM1.640183'),
            (3, 6, '1.SKB7.640196'), (3, 8, '1.SKD3.640198'),
            (3, 10, '1.SKD7.640191'), (3, 12, '1.SKD6.640190'),
            (3, 14, '1.SKB2.640194'), (3, 16, '1.SKM9.640192')]
        for row, col, sample_id in exp_positions:
            well = obs_layout[row - 1][col - 1]
            self.assertEqual(well.row, row)
            self.assertEqual(well.column, col)
            self.assertEqual(
                well.composition.gdna_composition.sample_composition.sample_id,
                sample_id)

        # In these positions we did not have an origin plate, do not store
        # anything, this way we can differentiate from blanks and save
        # reagents during library prep
        for col in range(0, 15):
            self.assertIsNone(obs_layout[1][col])

        self.assertEqual(obs.robot, Equipment(1))
        self.assertEqual(obs.gdna_plates, [ep1.plates[0], ep2.plates[0]])


class TestLibraryPrep16SProcess(LabControlTestCase):
    def test_attributes(self):
        tester = LibraryPrep16SProcess(1)
        self.assertEqual(tester.date,
                         _help_make_datetime('2017-10-25 02:10:25'))
        self.assertEqual(tester.personnel, User('test@foo.bar'))
        self.assertEqual(tester.process_id, 13)
        self.assertEqual(tester.mastermix, ReagentComposition(3))
        self.assertEqual(tester.water_lot, ReagentComposition(4))
        self.assertEqual(tester.epmotion, Equipment(8))
        self.assertEqual(tester.epmotion_tm300_tool, Equipment(16))
        self.assertEqual(tester.epmotion_tm50_tool, Equipment(17))
        self.assertEqual(tester.gdna_plate.id, 22)
        self.assertEqual(tester.primer_plate, Plate(11))
        self.assertEqual(tester.volume, 10)

    def test_create(self):
        user = User('test@foo.bar')
        master_mix = ReagentComposition(2)
        water = ReagentComposition(3)
        robot = Equipment(8)
        tm300_8_tool = Equipment(16)
        tm50_8_tool = Equipment(17)
        volume = 75
        plates = [(Plate(22), Plate(11))]
        obs = LibraryPrep16SProcess.create(
            user, Plate(22), Plate(11), 'New 16S plate', robot,
            tm300_8_tool, tm50_8_tool, master_mix, water, volume)
        self.assertTrue(_help_compare_timestamps(obs.date))
        self.assertEqual(obs.personnel, user)
        self.assertEqual(obs.mastermix, ReagentComposition(2))
        self.assertEqual(obs.water_lot, ReagentComposition(3))
        self.assertEqual(obs.epmotion, Equipment(8))
        self.assertEqual(obs.epmotion_tm300_tool, Equipment(16))
        self.assertEqual(obs.epmotion_tm50_tool, Equipment(17))
        self.assertEqual(obs.gdna_plate, Plate(22))
        self.assertEqual(obs.primer_plate, Plate(11))
        self.assertEqual(obs.volume, 75)

        # Check the generated plates
        obs_plates = obs.plates
        self.assertEqual(len(obs_plates), 1)
        obs_plate = obs_plates[0]
        self.assertIsInstance(obs_plate, Plate)
        self.assertEqual(obs_plate.external_id, 'New 16S plate')
        self.assertEqual(obs_plate.plate_configuration,
                         plates[0][0].plate_configuration)

        # Check the well in the plate
        plate_layout = obs_plate.layout
        for i, row in enumerate(plate_layout):
            for j, well in enumerate(row):
                if i == 7 and j == 11:
                    self.assertIsNone(well)
                else:
                    self.assertIsInstance(well, Well)
                    self.assertEqual(well.plate, obs_plate)
                    self.assertEqual(well.row, i + 1)
                    self.assertEqual(well.column, j + 1)
                    self.assertEqual(well.latest_process, obs)
                    obs_composition = well.composition
                    self.assertIsInstance(obs_composition,
                                          LibraryPrep16SComposition)
                    self.assertEqual(obs_composition.upstream_process, obs)
                    self.assertEqual(obs_composition.container, well)
                    self.assertEqual(obs_composition.total_volume, 75)

        # spot check a couple of elements
        sample_id = plate_layout[0][
            0].composition.gdna_composition.sample_composition.sample_id
        self.assertEqual(sample_id, '1.SKB1.640202')
        barcode = plate_layout[0][
            0].composition.primer_composition.primer_set_composition.barcode
        self.assertEqual(barcode, 'AGCCTTCGTCGC')


class TestNormalizationProcess(LabControlTestCase):
    def test_calculate_norm_vol(self):
        # 1st conc: happy path
        # 2nd conc: exercises resolution
        # 3rd conc: exercises NaN handling, max_vol
        # 4th conc: exercises max_vol
        # 5th conc: exercises min_vol
        dna_concs = np.array([2, 7.89, np.nan, .0, 2001])
        exp_vols = np.array([2500., 632.5, 3500., 3500., 25])
        obs_vols = NormalizationProcess._calculate_norm_vol(dna_concs)
        np.testing.assert_allclose(exp_vols, obs_vols)

    def test_attributes(self):
        tester = NormalizationProcess(1)
        self.assertEqual(tester.date,
                         _help_make_datetime('2017-10-25 19:10:25'))
        self.assertEqual(tester.personnel, User('test@foo.bar'))
        self.assertEqual(tester.process_id, 21)
        self.assertEqual(tester.quantification_process,
                         QuantificationProcess(3))
        self.assertEqual(tester.water_lot, ReagentComposition(4))
        exp = {'function': 'default',
               'parameters': {'total_volume': 3500, 'target_dna': 5,
                              'min_vol': 2.5, 'max_volume': 3500,
                              'resolution': 2.5, 'reformat': False}}
        self.assertEqual(tester.normalization_function_data, exp)
        self.assertEqual(tester.compressed_plate, Plate(24))

    def test_create(self):
        user = User('test@foo.bar')
        water = ReagentComposition(3)
        obs = NormalizationProcess.create(
            user, QuantificationProcess(3), water, 'Create-Norm plate 1')
        self.assertTrue(_help_compare_timestamps(obs.date))
        self.assertEqual(obs.personnel, user)
        self.assertEqual(obs.quantification_process,
                         QuantificationProcess(3))
        self.assertEqual(obs.water_lot, ReagentComposition(3))

        # Check the generated plates
        obs_plates = obs.plates
        self.assertEqual(len(obs_plates), 1)
        obs_plate = obs_plates[0]
        self.assertEqual(obs_plate.external_id, 'Create-Norm plate 1')
        # Spot check some wells in the plate
        plate_layout = obs_plate.layout
        self.assertEqual(plate_layout[0][0].composition.dna_volume, 415)
        self.assertEqual(plate_layout[0][0].composition.water_volume, 3085)

    def test_format_picklist(self):
        exp_picklist = (
            'Sample ID\tSource Plate Name\tSource Plate Type\tSource Well\t'
            'Concentration\tTransfer Volume\tDestination Plate Name\t'
            'Destination Well\n'
            'sam1\tWater\t384PP_AQ_BP2_HT\tA1\t2.0\t1000.0\tNormalizedDNA\t'
            'A1\n'
            'sam2\tWater\t384PP_AQ_BP2_HT\tA2\t7.89\t2867.5\tNormalizedDNA\t'
            'A2\n'
            'blank1\tWater\t384PP_AQ_BP2_HT\tB1\tnan\t0.0\tNormalizedDNA\tB1\n'
            'sam3\tWater\t384PP_AQ_BP2_HT\tB2\t0.0\t0.0\tNormalizedDNA\tB2\n'
            'sam1\tSample\t384PP_AQ_BP2_HT\tA1\t2.0\t2500.0\tNormalizedDNA\t'
            'A1\n'
            'sam2\tSample\t384PP_AQ_BP2_HT\tA2\t7.89\t632.5\tNormalizedDNA\t'
            'A2\n'
            'blank1\tSample\t384PP_AQ_BP2_HT\tB1\tnan\t3500.0\tNormalizedDNA\t'
            'B1\n'
            'sam3\tSample\t384PP_AQ_BP2_HT\tB2\t0.0\t3500.0\tNormalizedDNA\t'
            'B2')
        dna_vols = np.array([[2500., 632.5], [3500., 3500.]])
        water_vols = 3500 - dna_vols
        wells = np.array([['A1', 'A2'], ['B1', 'B2']])
        sample_names = np.array([['sam1', 'sam2'], ['blank1', 'sam3']])
        dna_concs = np.array([[2, 7.89], [np.nan, .0]])
        obs_picklist = NormalizationProcess._format_picklist(
            dna_vols, water_vols, wells, sample_names=sample_names,
            dna_concs=dna_concs)
        self.assertEqual(exp_picklist, obs_picklist)

        # test if switching dest wells
        exp_picklist = (
            'Sample ID\tSource Plate Name\tSource Plate Type\tSource Well\t'
            'Concentration\tTransfer Volume\tDestination Plate Name\t'
            'Destination Well\n'
            'sam1\tWater\t384PP_AQ_BP2_HT\tA1\t2.0\t1000.0\tNormalizedDNA\t'
            'D1\n'
            'sam2\tWater\t384PP_AQ_BP2_HT\tA2\t7.89\t2867.5\tNormalizedDNA\t'
            'D2\n'
            'blank1\tWater\t384PP_AQ_BP2_HT\tB1\tnan\t0.0\tNormalizedDNA\tE1\n'
            'sam3\tWater\t384PP_AQ_BP2_HT\tB2\t0.0\t0.0\tNormalizedDNA\tE2\n'
            'sam1\tSample\t384PP_AQ_BP2_HT\tA1\t2.0\t2500.0\tNormalizedDNA\t'
            'D1\n'
            'sam2\tSample\t384PP_AQ_BP2_HT\tA2\t7.89\t632.5\tNormalizedDNA\t'
            'D2\n'
            'blank1\tSample\t384PP_AQ_BP2_HT\tB1\tnan\t3500.0\tNormalizedDNA\t'
            'E1\n'
            'sam3\tSample\t384PP_AQ_BP2_HT\tB2\t0.0\t3500.0\tNormalizedDNA\t'
            'E2')
        dna_vols = np.array([[2500., 632.5], [3500., 3500.]])
        water_vols = 3500 - dna_vols
        wells = np.array([['A1', 'A2'], ['B1', 'B2']])
        dest_wells = np.array([['D1', 'D2'], ['E1', 'E2']])
        sample_names = np.array([['sam1', 'sam2'], ['blank1', 'sam3']])
        dna_concs = np.array([[2, 7.89], [np.nan, .0]])
        obs_picklist = NormalizationProcess._format_picklist(
            dna_vols, water_vols, wells, dest_wells=dest_wells,
            sample_names=sample_names, dna_concs=dna_concs)
        self.assertEqual(exp_picklist, obs_picklist)

    def test_generate_echo_picklist(self):
        obs = NormalizationProcess(2).generate_echo_picklist()
        self.assertEqual(obs, NORM_PROCESS_PICKLIST)

    def test_generate_echo_picklist_with_specimen_id(self):
        # HACK: the Study object in labcontrol can't modify specimen_id_column
        # hence we do this directly in SQL, if a test fails the transaction
        # will rollback, otherwise we reset the column to NULL.
        sql = """UPDATE qiita.study
                 SET specimen_id_column = %s
                 WHERE study_id = 1"""
        with sql_connection.TRN as TRN:
            TRN.add(sql, ['anonymized_name'])

            obs = NormalizationProcess(2).generate_echo_picklist()
            self.assertEqual(obs, NORM_PROCESS_PICKLIST_SID)

            TRN.add(sql, [None])


class TestQuantificationProcess(LabControlTestCase):
    def test_compute_pico_concentration(self):
        dna_vals = np.array([[10.14, 7.89, 7.9, 15.48],
                             [7.86, 8.07, 8.16, 9.64],
                             [12.29, 7.64, 7.32, 13.74]])
        obs = QuantificationProcess._compute_pico_concentration(
            dna_vals, size=400)
        exp = np.array([[38.4090909, 29.8863636, 29.9242424, 58.6363636],
                        [29.7727273, 30.5681818, 30.9090909, 36.5151515],
                        [46.5530303, 28.9393939, 27.7272727, 52.0454545]])
        npt.assert_allclose(obs, exp)

    def test_make_2D_array(self):
        example_qpcr_df = pd.DataFrame(
            {'Sample DNA Concentration': [12, 0, 5, np.nan],
             'Well': ['A1', 'A2', 'A3', 'A4']})
        exp_cp_array = np.array([[12.0, 0.0, 5.0, np.nan]])
        obs = QuantificationProcess._make_2D_array(
            example_qpcr_df, rows=1, cols=4).astype(float)
        np.testing.assert_allclose(obs, exp_cp_array)

        example2_qpcr_df = pd.DataFrame({'Cp': [12, 0, 1, np.nan,
                                                12, 0, 5, np.nan],
                                        'Pos': ['A1', 'A2', 'A3', 'A4',
                                                'B1', 'B2', 'B3', 'B4']})
        exp2_cp_array = np.array([[12.0, 0.0, 1.0, np.nan],
                                  [12.0, 0.0, 5.0, np.nan]])
        obs = QuantificationProcess._make_2D_array(
            example2_qpcr_df, data_col='Cp', well_col='Pos', rows=2,
            cols=4).astype(float)
        np.testing.assert_allclose(obs, exp2_cp_array)

    def test_rationalize_pico_csv_string(self):
        pico_csv1 = ('Results					\r'
                     '					\r'
                     'Well ID\tWell\t[Blanked-RFU]\t[Concentration]		\r'
                     'SPL1\tA1\t<0.000\t3.432		\r'
                     'SPL2\tA2\t4949.000\t3.239		\r'
                     'SPL3\tB1\t>15302.000\t10.016		\r'
                     'SPL4\tB2\t4039.000\t2.644		\r'
                     '					\r'
                     'Curve2 Fitting Results					\r'
                     '					\r'
                     'Curve Name\tCurve Formula\tA\tB\tR2\tFit F Prob\r'
                     'Curve2\tY=A*X+B\t1.53E+003\t0\t0.995\t?????')

        expected_output = (
            'Results					\n'
            '					\n'
            'Well ID\tWell\t[Blanked-RFU]\t[Concentration]		\n'
            'SPL1\tA1\t0.000\t3.432		\n'
            'SPL2\tA2\t4949.000\t3.239		\n'
            'SPL3\tB1\t15302.000\t10.016		\n'
            'SPL4\tB2\t4039.000\t2.644		\n'
            '					\n'
            'Curve2 Fitting Results					\n'
            '					\n'
            'Curve Name\tCurve Formula\tA\tB\tR2\tFit F Prob\n'
            'Curve2\tY=A*X+B\t1.53E+003\t0\t0.995\t?????')
        output1 = QuantificationProcess._rationalize_pico_csv_string(pico_csv1)
        self.assertEqual(output1, expected_output)

        pico_csv2 = ('Results					\r\n'
                     '					\r\n'
                     'Well ID\tWell\t[Blanked-RFU]\t[Concentration]		\r\n'
                     'SPL1\tA1\t<0.000\t3.432		\r\n'
                     'SPL2\tA2\t4949.000\t3.239		\r\n'
                     'SPL3\tB1\t>15302.000\t10.016		\r\n'
                     'SPL4\tB2\t4039.000\t2.644		\r\n'
                     '					\r\n'
                     'Curve2 Fitting Results					\r\n'
                     '					\r\n'
                     'Curve Name\tCurve Formula\tA\tB\tR2\tFit F Prob\r\n'
                     'Curve2\tY=A*X+B\t1.53E+003\t0\t0.995\t?????')
        output2 = QuantificationProcess._rationalize_pico_csv_string(pico_csv2)
        self.assertEqual(output2, expected_output)

    def test_parse_pico_csv(self):
        # Test a normal sheet
        pico_csv1 = '''Results

        Well ID\tWell\t[Blanked-RFU]\t[Concentration]
        SPL1\tA1\t5243.000\t3.432
        SPL2\tA2\t4949.000\t3.239
        SPL3\tB1\t15302.000\t10.016
        SPL4\tB2\t4039.000\t2.644

        Curve2 Fitting Results

        Curve Name\tCurve Formula\tA\tB\tR2\tFit F Prob
        Curve2\tY=A*X+B\t1.53E+003\t0\t0.995\t?????
        '''
        exp_pico_df1 = pd.DataFrame({'Well': ['A1', 'A2', 'B1', 'B2'],
                                    'Sample DNA Concentration':
                                        [3.432, 3.239, 10.016, 2.644]})
        obs_pico_df1 = QuantificationProcess._parse_pico_csv(pico_csv1)
        pd.testing.assert_frame_equal(obs_pico_df1, exp_pico_df1,
                                      check_like=True)

        # Test a sheet that has some ????, <, and > values
        pico_csv2 = '''Results

        Well ID\tWell\t[Blanked-RFU]\t[Concentration]
        SPL1\tA1\t5243.000\t>3.432
        SPL2\tA2\t4949.000\t<0.000
        SPL3\tB1\t15302.000\t10.016
        SPL4\tB2\t\t?????

        Curve2 Fitting Results

        Curve Name\tCurve Formula\tA\tB\tR2\tFit F Prob
        Curve2\tY=A*X+B\t1.53E+003\t0\t0.995\t?????
        '''
        exp_pico_df2 = pd.DataFrame({'Well': ['A1', 'A2', 'B1', 'B2'],
                                    'Sample DNA Concentration':
                                        [3.432, 0.000, 10.016, 10.016]})
        obs_pico_df2 = QuantificationProcess._parse_pico_csv(pico_csv2)
        pd.testing.assert_frame_equal(obs_pico_df2, exp_pico_df2,
                                      check_like=True)

        # Test a sheet that has unexpected value that can't be converted to #
        pico_csv3 = '''Results

        Well ID\tWell\t[Blanked-RFU]\t[Concentration]
        SPL1\tA1\t5243.000\t3.432
        SPL2\tA2\t4949.000\t3.239
        SPL3\tB1\t15302.000\t10.016
        SPL4\tB2\t\tfail

        Curve2 Fitting Results

        Curve Name\tCurve Formula\tA\tB\tR2\tFit F Prob
        Curve2\tY=A*X+B\t1.53E+003\t0\t0.995\t?????
        '''
        with self.assertRaises(ValueError):
            QuantificationProcess._parse_pico_csv(pico_csv3)

    def test_parse(self):
        # Test a normal sheet
        # Note that the pico output file sometimes has \r (NOT \r\n)
        # line endings
        pico_csv1 = ('Results					\r'
                     '					\r'
                     'Well ID\tWell\t[Blanked-RFU]\t[Concentration]		\r'
                     'SPL1\tA1\t5243.000\t3.432		\r'
                     'SPL2\tA2\t4949.000\t3.239		\r'
                     'SPL3\tB1\t15302.000\t10.016		\r'
                     'SPL4\tB2\t4039.000\t2.644		\r'
                     '					\r'
                     'Curve2 Fitting Results					\r'
                     '					\r'
                     'Curve Name\tCurve Formula\tA\tB\tR2\tFit F Prob\r'
                     'Curve2\tY=A*X+B\t1.53E+003\t0\t0.995\t?????')

        obs1 = QuantificationProcess.parse(pico_csv1)
        exp = np.asarray(
            [[3.432, 3.239, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan,
              np.nan, np.nan, np.nan, np.nan],
             [10.016, 2.644, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan,
              np.nan, np.nan, np.nan, np.nan],
             [np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan,
              np.nan, np.nan, np.nan, np.nan],
             [np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan,
              np.nan, np.nan, np.nan, np.nan],
             [np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan,
              np.nan, np.nan, np.nan, np.nan],
             [np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan,
              np.nan, np.nan, np.nan, np.nan],
             [np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan,
              np.nan, np.nan, np.nan, np.nan],
             [np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan,
              np.nan, np.nan, np.nan, np.nan]])

        npt.assert_allclose(obs1, exp)

        # other times (maybe using other plate readers/machines?) the
        # line endings are \r\n
        pico_csv2 = ('Results					\r\n'
                     '					\r\n'
                     'Well ID\tWell\t[Blanked-RFU]\t[Concentration]		\r\n'
                     'SPL1\tA1\t5243.000\t3.432		\r\n'
                     'SPL2\tA2\t4949.000\t3.239		\r\n'
                     'SPL3\tB1\t15302.000\t10.016		\r\n'
                     'SPL4\tB2\t4039.000\t2.644		\r\n'
                     '					\r\n'
                     'Curve2 Fitting Results					\r\n'
                     '					\r\n'
                     'Curve Name\tCurve Formula\tA\tB\tR2\tFit F Prob\r\n'
                     'Curve2\tY=A*X+B\t1.53E+003\t0\t0.995\t?????')
        obs2 = QuantificationProcess.parse(pico_csv2)
        npt.assert_allclose(obs2, exp)

    def test_attributes(self):
        tester = QuantificationProcess(1)
        self.assertEqual(tester.date,
                         _help_make_datetime('2017-10-25 19:10:05'))
        self.assertEqual(tester.personnel, User('test@foo.bar'))
        self.assertEqual(tester.process_id, 14)
        self.assertIsNone(tester.notes)
        obs = tester.concentrations
        # 380 because quantified 4 96-well plates in one process (and each
        # plate has one empty well, hence 380 rather than 384)
        self.assertEqual(len(obs), 380)
        self.assertEqual(obs[0],
                         (LibraryPrep16SComposition(1), 20.0, 60.606))
        self.assertEqual(obs[36],
                         (LibraryPrep16SComposition(37), 20.0, 60.606))
        self.assertEqual(obs[7],
                         (LibraryPrep16SComposition(8), 1.0, 3.0303))  # blank

        tester = QuantificationProcess(4)
        self.assertEqual(tester.date,
                         _help_make_datetime('2017-10-25 19:10:25'))
        self.assertEqual(tester.personnel, User('test@foo.bar'))
        self.assertEqual(tester.process_id, 23)
        self.assertIsNone(tester.notes)
        obs = tester.concentrations
        self.assertEqual(len(obs), 380)
        self.assertEqual(  # experimental sample
            obs[0], (LibraryPrepShotgunComposition(1), 12.068, 36.569))
        self.assertEqual(  # vibrio
            obs[6], (LibraryPrepShotgunComposition(7), 8.904, 26.981))
        self.assertEqual(  # blank
            obs[7], (LibraryPrepShotgunComposition(8), 0.342, 1.036))

        tester = QuantificationProcess(5)
        self.assertEqual(tester.date,
                         _help_make_datetime('2017-10-26 03:10:25'))
        self.assertEqual(tester.personnel, User('test@foo.bar'))
        self.assertEqual(tester.process_id, 27)
        self.assertEqual(tester.notes, "Requantification--oops")
        obs = tester.concentrations
        self.assertEqual(len(obs), 380)
        self.assertEqual(
            obs[0], (LibraryPrepShotgunComposition(1), 13.068, 38.569))
        self.assertEqual(
            obs[6], (LibraryPrepShotgunComposition(7), 9.904, 28.981))
        self.assertEqual(
            obs[7], (LibraryPrepShotgunComposition(8), 1.342, 3.036))

    def test_create(self):
        user = User('test@foo.bar')
        plate = Plate(23)
        concentrations = np.around(np.random.rand(8, 12), 6)

        # Add some known values for DNA concentration
        concentrations[0][0] = 3
        concentrations[0][1] = 4
        concentrations[0][2] = 40
        # Set blank wells to zero DNA concentrations
        concentrations[7] = np.zeros_like(concentrations[7])

        # add DNA concentrations to plate and check for sanity
        obs = QuantificationProcess.create(user, plate, concentrations)
        self.assertTrue(_help_compare_timestamps(obs.date))
        self.assertEqual(obs.personnel, user)
        obs_c = obs.concentrations
        self.assertEqual(len(obs_c), 95)
        self.assertEqual(obs_c[0][0], LibraryPrep16SComposition(1))
        npt.assert_almost_equal(obs_c[0][1], concentrations[0][0])
        self.assertIsNone(obs_c[0][2])
        self.assertEqual(obs_c[12][0], LibraryPrep16SComposition(2))  # B1
        npt.assert_almost_equal(obs_c[12][1], concentrations[1][0])
        self.assertIsNone(obs_c[12][2])

        # compute library concentrations (nM) from DNA concentrations (ng/uL)
        obs.compute_concentrations()
        obs_c = obs.concentrations
        # Check the values that we know
        npt.assert_almost_equal(obs_c[0][2], 9.09091)
        npt.assert_almost_equal(obs_c[1][2], 12.1212)
        npt.assert_almost_equal(obs_c[2][2], 121.212)
        # Last row are all 0 because they're blanks
        for i in range(84, 95):
            npt.assert_almost_equal(obs_c[i][2], 0)

        note = "a test note"
        concentrations = np.around(np.random.rand(16, 24), 6)
        # Add some known values
        concentrations[0][0] = 10.14
        concentrations[0][1] = 7.89
        plate = Plate(26)
        obs = QuantificationProcess.create(user, plate, concentrations, note)
        self.assertTrue(_help_compare_timestamps(obs.date))
        self.assertEqual(obs.personnel, user)
        obs_c = obs.concentrations
        self.assertEqual(len(obs_c), 380)
        self.assertEqual(obs_c[0][0], LibraryPrepShotgunComposition(1))
        npt.assert_almost_equal(obs_c[0][1], concentrations[0][0])
        self.assertIsNone(obs_c[0][2])
        obs.compute_concentrations(size=400)
        obs_c = obs.concentrations
        # Make sure that the known values are the ones that we expect
        npt.assert_almost_equal(obs_c[0][2], 38.4091)
        npt.assert_almost_equal(obs_c[1][2], 29.8864)

        # Test empty concentrations
        with self.assertRaises(ValueError):
            QuantificationProcess.create(user, plate, [])
        with self.assertRaises(ValueError):
            QuantificationProcess.create(user, plate, [[]])


class TestLibraryPrepShotgunProcess(LabControlTestCase):
    def test_attributes(self):
        tester = LibraryPrepShotgunProcess(1)
        self.assertEqual(tester.date,
                         _help_make_datetime('2017-10-25 19:10:25'))
        self.assertEqual(tester.personnel, User('test@foo.bar'))
        self.assertEqual(tester.process_id, 22)
        self.assertEqual(tester.kapa_hyperplus_kit, ReagentComposition(5))
        self.assertEqual(tester.stub_lot, ReagentComposition(6))
        self.assertEqual(tester.normalization_process, NormalizationProcess(1))
        self.assertEqual(tester.normalized_plate, Plate(25))
        self.assertEqual(tester.i5_primer_plate, Plate(19))
        self.assertEqual(tester.i7_primer_plate, Plate(20))
        self.assertEqual(tester.volume, 4000)

    def test_create(self):
        user = User('test@foo.bar')
        plate = Plate(25)
        kapa = ReagentComposition(4)
        stub = ReagentComposition(5)
        obs = LibraryPrepShotgunProcess.create(
            user, plate, 'Test Shotgun Library 1', kapa, stub, 4000,
            Plate(19), Plate(20))
        self.assertTrue(_help_compare_timestamps(obs.date))
        self.assertEqual(obs.personnel, user)
        self.assertEqual(obs.kapa_hyperplus_kit, kapa)
        self.assertEqual(obs.stub_lot, stub)
        self.assertEqual(obs.normalization_process, NormalizationProcess(1))
        self.assertEqual(obs.normalized_plate, Plate(25))
        self.assertEqual(obs.i5_primer_plate, Plate(19))
        self.assertEqual(obs.i7_primer_plate, Plate(20))
        self.assertEqual(obs.volume, 4000)

        plates = obs.plates
        self.assertEqual(len(plates), 1)

        # The code below is not generating a layout, just reading the layout
        # generated by LibraryPrepShotgunProcess.create into a
        # convenience format.
        # When LibraryPrepShotgunProcess.create makes obs, it fills the
        # obs.plates[0].layout property with a list of lists of lists of Wells.
        # This makes it very hard to create a test case: you have to know the
        # database id of each of the wells to instantiate all the expected Well
        # objects, and it is prohibitively time-consuming for the code to
        # instantiate them in the test case and compare them to all the Well
        # objects inobs.plates[0].layout.
        # Because of this, I chose to set up the part of the test that checks
        # whether the correct i5 and i7 primer has been assigned to the correct
        # well using a known-good as a list of lists of lists of strings: the
        # human-readable well id--A1, etc, the i7 primer name, and the
        # i5 primer name. The known-good, in this format, is stored in
        # SHOTGUN_PRIMER_LAYOUT. The code below is simply
        # extracting those strings from obs.plates[0].layout (into a
        # convenience variable obs_primer_layout) so that they can be compared
        # with the known-good via assertListEqual.
        # In the cases where a given Well object in obs.plates[0].layout is
        # None, of course you can't access its various nested string
        # properties, so None is returned instead of the strings.
        obs_primer_layout = []
        for row in obs.plates[0].layout:
            row_detail = []
            for well in row:
                well_detail = [None, None, None]
                if well is not None:
                    well_detail = [well.well_id,
                                   well.composition.i7_composition.
                                   primer_set_composition.external_id,
                                   well.composition.i5_composition.
                                   primer_set_composition.external_id]
                # end if well is not None
                row_detail.append(well_detail)
            obs_primer_layout.append(row_detail)

        self.assertListEqual(obs_primer_layout, SHOTGUN_PRIMER_LAYOUT)

    def test_format_picklist(self):
        exp_picklist = (
            'Sample ID\tSource Plate Name\tSource Plate Type\tSource Well\t'
            'Transfer Volume\tIndex Name\tIndex Sequence\t'
            'Destination Plate Name\tDestination Well\n'
            'sam1\tiTru5_plate\t384LDV_AQ_B2_HT\tA1\t250\tiTru5_01_A\tACCGACAA'
            '\tIndexPCRPlate\tA1\n'
            'sam2\tiTru5_plate\t384LDV_AQ_B2_HT\tB1\t250\tiTru5_01_B\tAGTGGCAA'
            '\tIndexPCRPlate\tA2\n'
            'blank1\tiTru5_plate\t384LDV_AQ_B2_HT\tC1\t250\tiTru5_01_C'
            '\tCACAGACT\tIndexPCRPlate\tB1\n'
            'sam3\tiTru5_plate\t384LDV_AQ_B2_HT\tD1\t250\tiTru5_01_D\tCGACACTT'
            '\tIndexPCRPlate\tB2\n'
            'sam1\tiTru7_plate\t384LDV_AQ_B2_HT\tA1\t250\tiTru7_101_01\t'
            'ACGTTACC\tIndexPCRPlate\tA1\n'
            'sam2\tiTru7_plate\t384LDV_AQ_B2_HT\tA2\t250\tiTru7_101_02\t'
            'CTGTGTTG\tIndexPCRPlate\tA2\n'
            'blank1\tiTru7_plate\t384LDV_AQ_B2_HT\tA3\t250\tiTru7_101_03\t'
            'TGAGGTGT\tIndexPCRPlate\tB1\n'
            'sam3\tiTru7_plate\t384LDV_AQ_B2_HT\tA4\t250\tiTru7_101_04\t'
            'GATCCATG\tIndexPCRPlate\tB2')

        sample_wells = np.array(['A1', 'A2', 'B1', 'B2'])
        sample_names = np.array(['sam1', 'sam2', 'blank1', 'sam3'])
        indices = pd.DataFrame({
            'i5 name': {0: 'iTru5_01_A', 1: 'iTru5_01_B', 2: 'iTru5_01_C',
                        3: 'iTru5_01_D'},
            'i5 plate': {0: 'iTru5_plate', 1: 'iTru5_plate', 2: 'iTru5_plate',
                         3: 'iTru5_plate'},
            'i5 sequence': {0: 'ACCGACAA', 1: 'AGTGGCAA', 2: 'CACAGACT',
                            3: 'CGACACTT'},
            'i5 well': {0: 'A1', 1: 'B1', 2: 'C1', 3: 'D1'},
            'i7 name': {0: 'iTru7_101_01', 1: 'iTru7_101_02',
                        2: 'iTru7_101_03', 3: 'iTru7_101_04'},
            'i7 plate': {0: 'iTru7_plate', 1: 'iTru7_plate', 2: 'iTru7_plate',
                         3: 'iTru7_plate'},
            'i7 sequence': {0: 'ACGTTACC', 1: 'CTGTGTTG', 2: 'TGAGGTGT',
                            3: 'GATCCATG'},
            'i7 well': {0: 'A1', 1: 'A2', 2: 'A3', 3: 'A4'},
            'index combo seq': {0: 'ACCGACAAACGTTACC', 1: 'AGTGGCAACTGTGTTG',
                                2: 'CACAGACTTGAGGTGT', 3: 'CGACACTTGATCCATG'}})
        obs_picklist = LibraryPrepShotgunProcess._format_picklist(
            sample_names, sample_wells, indices)
        self.assertEqual(exp_picklist, obs_picklist)

    def test_generate_echo_picklist(self):
        obs = LibraryPrepShotgunProcess(1).generate_echo_picklist()
        obs_lines = obs.splitlines()
        self.assertEqual(
            obs_lines[0],
            'Sample ID\tSource Plate Name\tSource Plate Type\tSource Well\t'
            'Transfer Volume\tIndex Name\tIndex Sequence\t'
            'Destination Plate Name\tDestination Well')
        self.assertEqual(
            obs_lines[1],
            '1.SKB1.640202.Test.plate.1.A1 (1.SKB1.640202)\tiTru_5_primer\t'
            '384LDV_AQ_B2_HT\tA1\t250\tiTru5_01_A\tACCGACAA\tIndexPCRPlate\t'
            'A1')
        self.assertEqual(
            obs_lines[-1],
            'blank.Test.plate.4.H11\tiTru_7_primer\t'
            '384LDV_AQ_B2_HT\tP2\t250\tiTru7_115_01\tCAAGGTCT\tIndexPCRPlate\t'
            'P22')

    def test_generate_echo_picklist_with_specimen_id(self):
        # HACK: the Study object in labcontrol can't modify specimen_id_column
        # hence we do this directly in SQL, if a test fails the transaction
        # will rollback, otherwise we reset the column to NULL.
        sql = """UPDATE qiita.study
                 SET specimen_id_column = %s
                 WHERE study_id = 1"""
        with sql_connection.TRN as TRN:
            TRN.add(sql, ['anonymized_name'])

            obs = LibraryPrepShotgunProcess(1).generate_echo_picklist()
            obs_lines = obs.splitlines()
            self.assertEqual(
                obs_lines[0],
                'Sample ID\tSource Plate Name\tSource Plate Type\tSource Well'
                '\tTransfer Volume\tIndex Name\tIndex Sequence\t'
                'Destination Plate Name\tDestination Well')
            self.assertEqual(
                obs_lines[1],
                '1.SKB1.640202.Test.plate.1.A1 (SKB1)\tiTru_5_primer\t'
                '384LDV_AQ_B2_HT\tA1\t250\tiTru5_01_A\tACCGACAA\t'
                'IndexPCRPlate\tA1')
            self.assertEqual(
                obs_lines[-1],
                'blank.Test.plate.4.H11\tiTru_7_primer\t384LDV_AQ_B2_HT\tP2\t'
                '250\tiTru7_115_01\tCAAGGTCT\tIndexPCRPlate\tP22')

            TRN.add(sql, [None])


class TestPoolingProcess(LabControlTestCase):
    def test_compute_pooling_values_eqvol(self):
        qpcr_conc = np.array(
            [[98.14626462, 487.8121413, 484.3480866, 2.183406934],
             [498.3536649, 429.0839787, 402.4270321, 140.1601735],
             [21.20533391, 582.9456031, 732.2655041, 7.545145988]])
        obs_sample_vols = PoolingProcess.compute_pooling_values_eqvol(
            qpcr_conc, total_vol=60.0)
        exp_sample_vols = np.zeros([3, 4]) + 5000
        npt.assert_allclose(obs_sample_vols, exp_sample_vols)

        obs_sample_vols = PoolingProcess.compute_pooling_values_eqvol(
            qpcr_conc, total_vol=60)
        npt.assert_allclose(obs_sample_vols, exp_sample_vols)

    def test_compute_pooling_values_minvol(self):
        sample_concs = np.array([[1, 12, 400], [200, 40, 1]])
        exp_vols = np.array([[100, 100, 4166.6666666666],
                             [8333.33333333333, 41666.666666666, 100]])
        obs_vols = PoolingProcess.compute_pooling_values_minvol(
            sample_concs, total=.01, floor_vol=100, floor_conc=40,
            total_each=False, vol_constant=10**9)
        npt.assert_allclose(exp_vols, obs_vols)

    def test_compute_pooling_values_minvol_amplicon(self):
        sample_concs = np.array([[1, 12, 40], [200, 40, 1]])
        exp_vols = np.array([[2, 2, 6],
                             [1.2, 6, 2]])
        obs_vols = PoolingProcess.compute_pooling_values_minvol(
            sample_concs)
        npt.assert_allclose(exp_vols, obs_vols)

    def test_adjust_blank_vols(self):
        pool_vols = np.array([[2, 2, 6],
                              [1.2, 6, 2]])

        pool_blanks = np.array([[True, False, False],
                                [False, False, True]])

        blank_vol = 1

        exp_vols = np.array([[1, 2, 6],
                             [1.2, 6, 1]])

        obs_vols = PoolingProcess.adjust_blank_vols(pool_vols,
                                                    pool_blanks,
                                                    blank_vol)

        npt.assert_allclose(obs_vols, exp_vols)

    def test_select_blanks(self):
        pool_vols = np.array([[2, 2, 6],
                              [1.2, 6, 2]])

        pool_concs = np.array([[3, 2, 6],
                               [1.2, 6, 2]])

        pool_blanks = np.array([[True, False, False],
                                [False, False, True]])

        exp_vols1 = np.array([[2, 2, 6],
                              [1.2, 6, 0]])

        obs_vols1 = PoolingProcess.select_blanks(pool_vols,
                                                 pool_concs,
                                                 pool_blanks,
                                                 1)

        npt.assert_allclose(obs_vols1, exp_vols1)

        exp_vols2 = np.array([[2, 2, 6],
                              [1.2, 6, 2]])

        obs_vols2 = PoolingProcess.select_blanks(pool_vols,
                                                 pool_concs,
                                                 pool_blanks,
                                                 2)

        npt.assert_allclose(obs_vols2, exp_vols2)

        exp_vols0 = np.array([[0, 2, 6],
                              [1.2, 6, 0]])

        obs_vols0 = PoolingProcess.select_blanks(pool_vols,
                                                 pool_concs,
                                                 pool_blanks,
                                                 0)

        npt.assert_allclose(obs_vols0, exp_vols0)

    def test_select_blanks_num_errors(self):
        pool_vols = np.array([[2, 2, 6],
                              [1.2, 6, 2]])

        pool_concs = np.array([[3, 2, 6],
                               [1.2, 6, 2]])

        pool_blanks = np.array([[True, False, False],
                                [False, False, True]])

        with self.assertRaisesRegex(ValueError, "(passed: -1)"):
            PoolingProcess.select_blanks(pool_vols,
                                         pool_concs,
                                         pool_blanks,
                                         -1)

    def test_select_blanks_shape_errors(self):
        pool_vols = np.array([[2, 2, 6],
                              [1.2, 6, 2],
                              [1.2, 6, 2]])

        pool_concs = np.array([[3, 2, 6],
                               [1.2, 6, 2]])

        pool_blanks = np.array([[True, False, False],
                                [False, False, True]])

        with self.assertRaisesRegex(ValueError, "all input arrays"):
            PoolingProcess.select_blanks(pool_vols,
                                         pool_concs,
                                         pool_blanks,
                                         2)

    def test_attributes(self):
        tester = PoolingProcess(1)
        self.assertEqual(tester.date,
                         _help_make_datetime('2017-10-25 19:10:25'))
        self.assertEqual(tester.personnel, User('test@foo.bar'))
        self.assertEqual(tester.process_id, 16)
        self.assertEqual(tester.quantification_process,
                         QuantificationProcess(1))
        self.assertEqual(tester.robot, Equipment(8))
        self.assertEqual(tester.destination, '1')
        self.assertEqual(tester.pool, PoolComposition(1))
        components = tester.components
        self.assertEqual(len(components), 95)
        self.assertEqual(
            components[0], (LibraryPrep16SComposition(1), 1.0))
        self.assertEqual(
            components[36], (LibraryPrep16SComposition(37), 1.0))
        self.assertEqual(
            components[94], (LibraryPrep16SComposition(95), 1.0))

    def test_create(self):
        user = User('test@foo.bar')
        quant_proc = QuantificationProcess(1)
        robot = Equipment(8)
        input_compositions = [
            {'composition': Composition.factory(1544), 'input_volume': 1,
             'percentage_of_output': 0.25},
            {'composition': Composition.factory(1547), 'input_volume': 1,
             'percentage_of_output': 0.25},
            {'composition': Composition.factory(1550), 'input_volume': 1,
             'percentage_of_output': 0.25},
            {'composition': Composition.factory(1553), 'input_volume': 1,
             'percentage_of_output': 0.25}]
        func_data = {"function": "amplicon",
                     "parameters": {"dna_amount": 240, "min_val": 1,
                                    "max_val": 15, "blank_volume": 2}}
        obs = PoolingProcess.create(user, quant_proc, 'New test pool name', 4,
                                    input_compositions, func_data, robot, '1')
        self.assertTrue(_help_compare_timestamps(obs.date))
        self.assertEqual(obs.personnel, user)
        self.assertEqual(obs.quantification_process, quant_proc)
        self.assertEqual(obs.robot, robot)
        self.assertEqual(obs.pooling_function_data, func_data)

    def test_format_picklist(self):
        # input volumes from a hypothetical 3x4 plate
        vol_sample = np.array([
            [10.00, 10.00, np.nan],
            [5.00, 10.00, 10.00],
            [10.00, 10.00, 10.00],
            [10.00, np.nan, 10.00]
        ])

        exp_header = 'Source Plate Name,Source Plate Type,Source Well,' \
                     'Concentration,Transfer Volume,Destination Plate Name,' \
                     'Destination Well\n'
        exp_body = """1,384LDV_AQ_B2_HT,A1,,10.00,NormalizedDNA,A1
1,384LDV_AQ_B2_HT,A2,,10.00,NormalizedDNA,A1
1,384LDV_AQ_B2_HT,A3,,0.00,NormalizedDNA,A1
1,384LDV_AQ_B2_HT,B1,,5.00,NormalizedDNA,A1
1,384LDV_AQ_B2_HT,B2,,10.00,NormalizedDNA,A2
1,384LDV_AQ_B2_HT,B3,,10.00,NormalizedDNA,A2
1,384LDV_AQ_B2_HT,C1,,10.00,NormalizedDNA,B1
1,384LDV_AQ_B2_HT,C2,,10.00,NormalizedDNA,B1
1,384LDV_AQ_B2_HT,C3,,10.00,NormalizedDNA,B2
1,384LDV_AQ_B2_HT,D1,,10.00,NormalizedDNA,B2
1,384LDV_AQ_B2_HT,D2,,0.00,NormalizedDNA,B2
1,384LDV_AQ_B2_HT,D3,,10.00,NormalizedDNA,C1"""
        exp_str = exp_header+exp_body

        obs_str = PoolingProcess._format_picklist(
            vol_sample, max_vol_per_well=26, dest_plate_shape=[3, 2])
        self.assertEqual(exp_str, obs_str)

    def test_format_picklist_error_dest_plate_too_small(self):
        # input volumes from a hypothetical 3x4 plate
        vol_sample = np.array([
            [10.00, 10.00, np.nan],
            [5.00, 10.00, 10.00],
            [10.00, 10.00, 10.00],
            [10.00, np.nan, 10.00]
        ])

        exp_err = "Destination well should be in row 3 but destination " \
                  "plate has only 2 rows"
        with self.assertRaisesRegex(ValueError, exp_err):
            PoolingProcess._format_picklist(vol_sample, max_vol_per_well=26,
                                            dest_plate_shape=[2, 2])

    def test_format_picklist_error_input_vol_too_large(self):
        # input volumes from a hypothetical 3x4 plate
        vol_sample = np.array([
            [1.00, 1.00, np.nan],
            [5.00, 10.00, 1.00],
            [1.00, 1.00, 10.00],
            [10.00, np.nan, 10.00]
        ])

        exp_err = "Volume 10.0 in input well B2 exceeds maximum volume per " \
                  "well of 7"
        with self.assertRaisesRegex(ValueError, exp_err):
            PoolingProcess._format_picklist(vol_sample, max_vol_per_well=7,
                                            dest_plate_shape=[3, 2])

    def test_format_picklist_error_too_many_rows(self):
        # input volumes from a hypothetical 32x48 plate
        vol_sample = np.ones((32, 48))

        exp_err = "Row letter generation for >26 wells is not supported"
        with self.assertRaisesRegex(ValueError, exp_err):
            PoolingProcess._format_picklist(vol_sample, max_vol_per_well=7,
                                            dest_plate_shape=[32, 48])

    def test_generate_echo_picklist_default(self):
        # With the default max_vol_per_well value of 30000 nL
        # (and with anything higher than that, such as the past default of
        # 60000 nL), this pooling process puts all components into A1
        obs = PoolingProcess(3).generate_echo_picklist()
        self.assertEqual(obs, POOLING_PROCESS_ECHO_PICKLIST)

    def test_generate_echo_picklist_nondefault_volume(self):
        # Setting the max_vol_per_well value to 1 nL, which is the volume in
        # each non-empty input well in PoolingProcess(3), puts the contents of
        # one non-empty input well into each output well.
        obs = PoolingProcess(3).generate_echo_picklist(1)
        self.assertEqual(obs, LOW_MAX_VOL_POOLING_PROCESS_ECHO_PICKLIST)

    def test_generate_epmotion_file(self):
        obs = PoolingProcess(1).generate_epmotion_file()
        obs_lines = obs.splitlines()
        self.assertEqual(
            obs_lines[0], 'Rack,Source,Rack,Destination,Volume,Tool')
        self.assertEqual(obs_lines[1], '1,A1,1,1,1.000,1')
        self.assertEqual(obs_lines[-1], '1,G12,1,1,1.000,1')

    def test_generate_pool_file(self):
        self.assertTrue(PoolingProcess(1).generate_pool_file().startswith(
            'Rack,Source,Rack,Destination,Volume,Tool'))
        self.assertTrue(PoolingProcess(3).generate_pool_file().startswith(
            'Source Plate Name,Source Plate Type,Source Well,Concentration,'))
        with self.assertRaises(ValueError):
            PoolingProcess(2).generate_pool_file()


class TestSequencingProcess(LabControlTestCase):
    def test_attributes(self):
        tester = SequencingProcess(1)
        self.assertEqual(tester.date,
                         _help_make_datetime('2017-10-25 19:10:25'))
        self.assertEqual(tester.personnel, User('test@foo.bar'))
        self.assertEqual(tester.process_id, 18)
        self.assertEqual(tester.pools, [[PoolComposition(2), 1]])
        self.assertEqual(tester.run_name, 'Test Run.1')
        self.assertEqual(tester.experiment, 'TestExperiment1')
        self.assertEqual(tester.sequencer, Equipment(18))
        self.assertEqual(tester.fwd_cycles, 151)
        self.assertEqual(tester.rev_cycles, 151)

        assay = PoolComposition.get_assay_type_for_sequencing_process(1)
        self.assertEqual(assay, 'Amplicon')

        self.assertEqual(tester.principal_investigator, User('test@foo.bar'))
        self.assertEqual(
            tester.contacts,
            [User('admin@foo.bar'), User('demo@microbio.me'),
             User('shared@foo.bar')])

    def test_list_sequencing_runs(self):
        obs = SequencingProcess.list_sequencing_runs()

        exp = {'process_id': 18,
                'run_name': 'Test Run.1',
                'sequencing_process_id': 1,
                'experiment': 'TestExperiment1',
                'sequencer_id': 18,
                'fwd_cycles': 151,
                'rev_cycles': 151,
                'principal_investigator': 'test@foo.bar'}

        self.assertDictEqual(obs[0], exp)

        exp = {'process_id': 25,
                'run_name': 'TestShotgunRun1',
                'sequencing_process_id': 2,
                'experiment': 'TestExperimentShotgun1',
                'sequencer_id': 19,
                'fwd_cycles': 151,
                'rev_cycles': 151,
                'principal_investigator': 'test@foo.bar'}

        self.assertDictEqual(obs[1], exp)

    def test_create(self):
        user = User('test@foo.bar')
        pool = PoolComposition(2)
        sequencer = Equipment(19)

        obs = SequencingProcess.create(
            user, [pool], 'TestCreateRun1', 'TestCreateExperiment1', sequencer,
            151, 151, user, contacts=[
                User('shared@foo.bar'), User('admin@foo.bar'),
                User('demo@microbio.me')])

        self.assertTrue(_help_compare_timestamps(obs.date))
        self.assertEqual(obs.personnel, user)
        self.assertEqual(obs.pools, [[PoolComposition(2), 1]])
        self.assertEqual(obs.run_name, 'TestCreateRun1')
        self.assertEqual(obs.experiment, 'TestCreateExperiment1')
        self.assertEqual(obs.sequencer, Equipment(19))
        self.assertEqual(obs.fwd_cycles, 151)
        self.assertEqual(obs.rev_cycles, 151)

        #self.assertEqual(obs.assay, 'Amplicon')
        assay = PoolComposition.get_assay_type_for_sequencing_process(obs.id)
        self.assertEqual(assay, 'Amplicon')

        self.assertEqual(obs.principal_investigator, User('test@foo.bar'))
        self.assertEqual(
            obs.contacts,
            [User('admin@foo.bar'), User('demo@microbio.me'),
             User('shared@foo.bar')])

    def test_bcl_scrub_name(self):
        self.assertEqual(Sheet._bcl_scrub_name('test.1'), 'test_1')
        self.assertEqual(Sheet._bcl_scrub_name('test-1'), 'test-1')
        self.assertEqual(Sheet._bcl_scrub_name('test_1'), 'test_1')

    def test__folder_scrub_name(self):
        input_str = "Ogden  Bogden-Meade*,_Pat O'Brien_1"
        exp = "Ogden_Bogden-Meade-_Pat_O-Brien_1"
        obs = Sheet._folder_scrub_name(input_str)
        self.assertEqual(obs, exp)

    def test_reverse_complement(self):
        self.assertEqual(
            SampleSheet._reverse_complement('AGCCT'), 'AGGCT')

    def test_sequencer_i5_index(self):
        indices = ['AGCT', 'CGGA', 'TGCC']
        exp_rc = ['AGCT', 'TCCG', 'GGCA']

        obs_hiseq4k = SampleSheet._sequencer_i5_index(
            'HiSeq4000', indices)
        self.assertListEqual(obs_hiseq4k, exp_rc)

        obs_hiseq25k = SampleSheet._sequencer_i5_index(
            'HiSeq2500', indices)
        self.assertListEqual(obs_hiseq25k, indices)

        obs_nextseq = SampleSheet._sequencer_i5_index(
            'NextSeq', indices)
        self.assertListEqual(obs_nextseq, exp_rc)

        with self.assertRaises(ValueError):
            SampleSheet._sequencer_i5_index('foo', indices)

    def test_format_sample_sheet_data(self):
        # test that single lane works - note there is no 16S counterpart for
        # the method being tested here.
        exp_data = (
            'Lane,Sample_ID,Sample_Name,Sample_Plate'
            ',Sample_Well,I7_Index_ID,index,I5_Index_ID'
            ',index2,Sample_Project,Well_Description\n'
            '1,blank1,blank1,example,B1,iTru7_101_03,TGAGGTGT,'
            'iTru5_01_C,CACAGACT,,\n'
            '1,sam1,sam1,example,A1,iTru7_101_01,ACGTTACC,'
            'iTru5_01_A,ACCGACAA,labperson1_pi1_studyId1,\n'
            '1,sam2,sam2,example,A2,iTru7_101_02,CTGTGTTG,'
            'iTru5_01_B,AGTGGCAA,labperson1_pi1_studyId1,\n'
            '1,sam3,sam3,example,B2,iTru7_101_04,GATCCATG,'
            'iTru5_01_D,CGACACTT,labperson1_pi1_studyId1,'
            )

        wells = ['A1', 'A2', 'B1', 'B2']
        sample_ids = ['sam1', 'sam2', 'blank1', 'sam3']
        sample_projs = ["labperson1_pi1_studyId1", "labperson1_pi1_studyId1",
                        "", "labperson1_pi1_studyId1"]
        i5_name = ['iTru5_01_A', 'iTru5_01_B', 'iTru5_01_C', 'iTru5_01_D']
        i5_seq = ['ACCGACAA', 'AGTGGCAA', 'CACAGACT', 'CGACACTT']
        i7_name = ['iTru7_101_01', 'iTru7_101_02',
                   'iTru7_101_03', 'iTru7_101_04']
        i7_seq = ['ACGTTACC', 'CTGTGTTG', 'TGAGGTGT', 'GATCCATG']
        sample_plates = ['example'] * 4

        obs_data = SampleSheetShotgun._format_sample_sheet_data(
            sample_ids, i7_name, i7_seq, i5_name, i5_seq, sample_projs,
            wells=wells, sample_plates=sample_plates, lanes=[1])
        self.assertEqual(obs_data, exp_data)

        # test that two lanes works
        exp_data_2 = (
            'Lane,Sample_ID,Sample_Name,Sample_Plate,'
            'Sample_Well,I7_Index_ID,index,I5_Index_ID,'
            'index2,Sample_Project,Well_Description\n'
            '1,blank1,blank1,example,B1,iTru7_101_03,TGAGGTGT,'
            'iTru5_01_C,CACAGACT,,\n'
            '1,sam1,sam1,example,A1,iTru7_101_01,ACGTTACC,'
            'iTru5_01_A,ACCGACAA,labperson1_pi1_studyId1,\n'
            '1,sam2,sam2,example,A2,iTru7_101_02,CTGTGTTG,'
            'iTru5_01_B,AGTGGCAA,labperson1_pi1_studyId1,\n'
            '1,sam3,sam3,example,B2,iTru7_101_04,GATCCATG,'
            'iTru5_01_D,CGACACTT,labperson1_pi1_studyId1,\n'
            '2,blank1,blank1,example,B1,iTru7_101_03,TGAGGTGT'
            ',iTru5_01_C,CACAGACT,,\n'
            '2,sam1,sam1,example,A1,iTru7_101_01,ACGTTACC,'
            'iTru5_01_A,ACCGACAA,labperson1_pi1_studyId1,\n'
            '2,sam2,sam2,example,A2,iTru7_101_02,CTGTGTTG,'
            'iTru5_01_B,AGTGGCAA,labperson1_pi1_studyId1,\n'
            '2,sam3,sam3,example,B2,iTru7_101_04,GATCCATG'
            ',iTru5_01_D,CGACACTT,labperson1_pi1_studyId1,')

        obs_data_2 = SampleSheetShotgun._format_sample_sheet_data(
            sample_ids, i7_name, i7_seq, i5_name, i5_seq, sample_projs,
            wells=wells, sample_plates=sample_plates, lanes=[1, 2])
        self.assertEqual(obs_data_2, exp_data_2)

        # test with r/c i5 barcodes
        exp_data = (
            'Lane,Sample_ID,Sample_Name,Sample_Plate'
            ',Sample_Well,I7_Index_ID,index,I5_Index_ID'
            ',index2,Sample_Project,Well_Description\n'
            '1,blank1,blank1,example,B1,iTru7_101_03,TGAGGTGT,'
            'iTru5_01_C,CACAGACT,,\n'
            '1,sam1,sam1,example,A1,iTru7_101_01,ACGTTACC,'
            'iTru5_01_A,ACCGACAA,labperson1_pi1_studyId1,\n'
            '1,sam2,sam2,example,A2,iTru7_101_02,CTGTGTTG,'
            'iTru5_01_B,AGTGGCAA,labperson1_pi1_studyId1,\n'
            '1,sam3,sam3,example,B2,iTru7_101_04,GATCCATG,'
            'iTru5_01_D,CGACACTT,labperson1_pi1_studyId1,')

        i5_seq = ['ACCGACAA', 'AGTGGCAA', 'CACAGACT', 'CGACACTT']
        obs_data = SampleSheetShotgun._format_sample_sheet_data(
            sample_ids, i7_name, i7_seq, i5_name, i5_seq, sample_projs,
            wells=wells, sample_plates=sample_plates, lanes=[1])
        self.assertEqual(obs_data, exp_data)

        # Test without header
        exp_data = (
            '1,blank1,blank1,example,B1,iTru7_101_03,TGAGGTGT,'
            'iTru5_01_C,CACAGACT,,\n'
            '1,sam1,sam1,example,A1,iTru7_101_01,ACGTTACC,'
            'iTru5_01_A,ACCGACAA,labperson1_pi1_studyId1,\n'
            '1,sam2,sam2,example,A2,iTru7_101_02,CTGTGTTG,'
            'iTru5_01_B,AGTGGCAA,labperson1_pi1_studyId1,\n'
            '1,sam3,sam3,example,B2,iTru7_101_04,GATCCATG,'
            'iTru5_01_D,CGACACTT,labperson1_pi1_studyId1,')

        obs_data = SampleSheetShotgun._format_sample_sheet_data(
            sample_ids, i7_name, i7_seq, i5_name, i5_seq, sample_projs,
            wells=wells, sample_plates=sample_plates, lanes=[1],
            include_header=False)
        self.assertEqual(obs_data, exp_data)

        # Test without lane index (for single-lane sequencers)
        exp_data = (
            'Sample_ID,Sample_Name,Sample_Plate'
            ',Sample_Well,I7_Index_ID,index,I5_Index_ID'
            ',index2,Sample_Project,Well_Description\n'
            'blank1,blank1,example,B1,iTru7_101_03,TGAGGTGT,'
            'iTru5_01_C,CACAGACT,,\n'
            'sam1,sam1,example,A1,iTru7_101_01,ACGTTACC,'
            'iTru5_01_A,ACCGACAA,labperson1_pi1_studyId1,\n'
            'sam2,sam2,example,A2,iTru7_101_02,CTGTGTTG,'
            'iTru5_01_B,AGTGGCAA,labperson1_pi1_studyId1,\n'
            'sam3,sam3,example,B2,iTru7_101_04,GATCCATG,'
            'iTru5_01_D,CGACACTT,labperson1_pi1_studyId1,')

        obs_data = SampleSheetShotgun._format_sample_sheet_data(
            sample_ids, i7_name, i7_seq, i5_name, i5_seq, sample_projs,
            wells=wells, sample_plates=sample_plates, lanes=[1],
            include_lane=False)
        self.assertEqual(obs_data, exp_data)

    def test_format_sample_sheet_comments(self):
        contacts = {'Test User': 'tuser@fake.com',
                    'Another User': 'anuser@fake.com',
                    'Jon Jonny': 'jonjonny@foo.com',
                    'Gregorio Orio': 'gregOrio@foo.com'}
        principal_investigator = {'Knight': 'theknight@fake.com'}
        other = None
        sep = '\t'
        exp_comment = (
            'PI\tKnight\ttheknight@fake.com\n'
            'Contact\tAnother User\tGregorio Orio'
            '\tJon Jonny\tTest User\n'
            'Contact emails\tanuser@fake.com\tgregOrio@foo.com'
            '\tjonjonny@foo.com\ttuser@fake.com\n')
        obs_comment = SampleSheet16S._format_sample_sheet_comments(
            principal_investigator, contacts, other, sep)
        self.assertEqual(exp_comment, obs_comment)

    def test___set_control_values_to_plate_value_success(self):
        plate_col_name = "Sample_Plate"
        projname_col_name = "Project name"
        input_indexes = ['1.SKB1.640202.Test.plate.1.A1',
                         '1.SKB6.640176.Test.plate.1.F5',
                         'vibrio.positive.control.Test.plate.1.G1',
                         'blank.Test.plate.1.H8',
                         '1.SKB1.990202.Test.plate.3.A1',
                         '1.SKB6.990176.Test.plate.3.F5',
                         'vibrio.positive.control.Test.plate.3.G6',
                         'blank.Test.plate.3.H1']
        input_vals = [('Test plate 1','Cannabis Soils'),
                      ('Test plate 1','Cannabis Soils'),
                      ('Test plate 1', None),
                      ('Test plate 1', None),
                      ('Test plate 3', 'Cannabis Soils'),
                      ('Test plate 3', 'Cannabis Soils'),
                      ('Test plate 3', None),
                      ('Test plate 3', None)]
        exp_vals = [('Test plate 1','Cannabis Soils'),
                      ('Test plate 1','Cannabis Soils'),
                      ('Test plate 1', 'Cannabis Soils'),
                      ('Test plate 1', 'Cannabis Soils'),
                      ('Test plate 3', 'Cannabis Soils'),
                      ('Test plate 3', 'Cannabis Soils'),
                      ('Test plate 3', 'Cannabis Soils'),
                      ('Test plate 3', 'Cannabis Soils')]
        input_df = pandas.DataFrame(input_vals,
                             columns=[plate_col_name, projname_col_name],
                             index=input_indexes)
        exp_df = pandas.DataFrame(exp_vals,
                             columns=[plate_col_name, projname_col_name],
                             index=input_indexes)

        obs_df = Sheet._set_control_values_to_plate_value(
            input_df, plate_col_name, projname_col_name)

        pandas.testing.assert_frame_equal(exp_df, obs_df)

    def test___set_control_values_to_plate_value_error(self):
        plate_col_name = "Sample_Plate"
        projname_col_name = "Project name"
        input_indexes = ['1.SKB1.640202.Test.plate.1.A1',
                         '1.SKB6.640176.Test.plate.1.F5',
                         'vibrio.positive.control.Test.plate.1.G1',
                         'blank.Test.plate.1.H8',
                         '1.SKB1.990202.Test.plate.2.A1',
                         '1.SKB6.990176.Test.plate.2.F5',
                         'vibrio.positive.control.Test.plate.2.G6',
                         'blank.Test.plate.2.H1',
                         'blank.Test.plate.3.A1',
                         'blank.Test.plate.3.C5',
                         'vibrio.positive.control.Test.plate.3.G6',
                         'blank.Test.plate.3.H1']
        input_vals = [('Test plate 1','Cannabis Soils'),
                      ('Test plate 1','Snake Soils'),
                      ('Test plate 1', None),
                      ('Test plate 1', None),
                      ('Test plate 2', 'Cannabis Soils'),
                      ('Test plate 2', 'Cannabis Soils'),
                      ('Test plate 2', None),
                      ('Test plate 2', None),
                      ('Test plate 3', None),
                      ('Test plate 3', None),
                      ('Test plate 3', None),
                      ('Test plate 3', None)]

        input_df = pandas.DataFrame(input_vals,
                             columns=[plate_col_name, projname_col_name],
                             index=input_indexes)

        exp_err = "Expected one unique value for plate 'Test plate 1' but " \
                  "received 2: Cannabis Soils, Snake Soils\nExpected one " \
                  "unique value for plate 'Test plate 3' but received 0:"
        with self.assertRaisesRegex(ValueError, exp_err):
            Sheet._set_control_values_to_plate_value(
                input_df, plate_col_name, projname_col_name)

    def test___set_control_values_to_plate_value_assert_platename_fail(self):
        plate_col_name = "Sample_Plate"
        projname_col_name = "Project name"
        input_indexes = ['1.SKB1.640202.Test.plate.1.A1',
                         '1.SKB6.640176.Test.plate.1.F5',
                         'vibrio.positive.control.Test.plate.1.G1',
                         'blank.Test.plate.1.H8',
                         '1.SKB1.990202.Test.plate.3.A1',
                         '1.SKB6.990176.Test.plate.3.F5',
                         'vibrio.positive.control.Test.plate.3.G6',
                         'blank.Test.plate.3.H1']
        input_vals = [('Test plate 1','Cannabis Soils'),
                      ('Test plate 1','Cannabis Soils'),
                      ('Test plate 1', None),
                      ('Test plate 1', None),
                      ('Test plate 3', 'Cannabis Soils'),
                      ('Test plate 3', 'Cannabis Soils'),
                      ('Test plate 3', None),
                      ('Test plate 3', None)]
        input_df = pandas.DataFrame(input_vals,
                             columns=["blue", projname_col_name],
                             index=input_indexes)

        with self.assertRaises(AssertionError):
            Sheet._set_control_values_to_plate_value(
                input_df, plate_col_name, projname_col_name)

    def test___set_control_values_to_plate_value_assert_projname_fail(self):
        plate_col_name = "Sample_Plate"
        projname_col_name = "Project name"
        input_indexes = ['1.SKB1.640202.Test.plate.1.A1',
                         '1.SKB6.640176.Test.plate.1.F5',
                         'vibrio.positive.control.Test.plate.1.G1',
                         'blank.Test.plate.1.H8',
                         '1.SKB1.990202.Test.plate.3.A1',
                         '1.SKB6.990176.Test.plate.3.F5',
                         'vibrio.positive.control.Test.plate.3.G6',
                         'blank.Test.plate.3.H1']
        input_vals = [('Test plate 1','Cannabis Soils'),
                      ('Test plate 1','Cannabis Soils'),
                      ('Test plate 1', None),
                      ('Test plate 1', None),
                      ('Test plate 3', 'Cannabis Soils'),
                      ('Test plate 3', 'Cannabis Soils'),
                      ('Test plate 3', None),
                      ('Test plate 3', None)]
        input_df = pandas.DataFrame(input_vals,
                             columns=[plate_col_name, "blue"],
                             index=input_indexes)

        with self.assertRaises(AssertionError):
            Sheet._set_control_values_to_plate_value(
                input_df, plate_col_name, projname_col_name)

    def test_format_sample_sheet(self):
        tester2 = SequencingProcess(2)
        tester2_date = datetime.strftime(
            tester2.date, Process.get_date_format())
        # Note: cannot hard-code the date in the below known-good text
        # because date string representation is specific to time-zone in
        # which system running the tests is located!
        exp2 = (
            '# PI,Dude,test@foo.bar',
            '# Contact,Demo,Shared',
            '# Contact emails,demo@microbio.me,shared@foo.bar',
            '[Header]',
            'IEMFileVersion\t4',
            'Investigator Name\tDude',
            'Experiment Name\tTestExperimentShotgun1',
            'Date\t' + tester2_date,
            'Workflow\tGenerateFASTQ',
            'Application\tFASTQ Only',
            'Assay\tMetagenomics',
            'Description\t',
            'Chemistry\tDefault',
            '',
            '[Reads]',
            '151',
            '151',
            '',
            '[Settings]',
            'ReverseComplement\t0',
            '',
            '[Data]\n'
            'Sample_ID\tSample_Name\tSample_Plate\tSample_Well'
            '\tI7_Index_ID\tindex\tI5_Index_ID\tindex2\tSample_Project'
            '\tWell_Description',
            'sam1\tsam1\texample\tA1\tiTru7_101_01\tACGTTACC\tiTru5_01_A'
            '\tACCGACAA\texample_proj\t',
            'sam2\tsam2\texample\tA2\tiTru7_101_02\tCTGTGTTG\tiTru5_01_B'
            '\tAGTGGCAA\texample_proj\t',
            'blank1\tblank1\texample\tB1\tiTru7_101_03\tTGAGGTGT\t'
            'iTru5_01_C\tCACAGACT\texample_proj\t',
            'sam3\tsam3\texample\tB2\tiTru7_101_04\tGATCCATG\tiTru5_01_D'
            '\tCGACACTT\texample_proj\t')

        data = (
            'Sample_ID\tSample_Name\tSample_Plate\tSample_Well\t'
            'I7_Index_ID\tindex\tI5_Index_ID\tindex2\tSample_Project\t'
            'Well_Description\n'
            'sam1\tsam1\texample\tA1\tiTru7_101_01\tACGTTACC\t'
            'iTru5_01_A\tACCGACAA\texample_proj\t\n'
            'sam2\tsam2\texample\tA2\tiTru7_101_02\tCTGTGTTG\t'
            'iTru5_01_B\tAGTGGCAA\texample_proj\t\n'
            'blank1\tblank1\texample\tB1\tiTru7_101_03\tTGAGGTGT\t'
            'iTru5_01_C\tCACAGACT\texample_proj\t\n'
            'sam3\tsam3\texample\tB2\tiTru7_101_04\tGATCCATG\t'
            'iTru5_01_D\tCGACACTT\texample_proj\t'
            )

        exp_sample_sheet = "\n".join(exp2)

        sp_id = tester2.id
        assay_t = PoolComposition.get_assay_type_for_sequencing_process(sp_id)
        params = {'include_lane': tester2.include_lane,
                  'pools': tester2.pools,
                  'principal_investigator': tester2.principal_investigator,
                  'contacts': tester2.contacts,
                  'experiment': tester2.experiment,
                  'date': tester2.date,
                  'fwd_cycles': tester2.fwd_cycles,
                  'rev_cycles': tester2.rev_cycles,
                  'run_name': tester2.run_name,
                  'sequencer': tester2.sequencer,
                  'assay_type': assay_t,
                  'sequencing_process_id': sp_id}

        sheet = SampleSheet.factory(**params)
        obs_sample_sheet = sheet._format_sample_sheet(data, sep='\t')
        self.assertEqual(exp_sample_sheet, obs_sample_sheet)

    def test_generate_sample_sheet_amplicon_single_lane(self):
        # Amplicon run, single lane
        tester = SequencingProcess(1)
        tester_date = datetime.strftime(tester.date, Process.get_date_format())
        # Note: cannot hard-code the date in the below known-good text
        # because date string representation is specific to time-zone in
        # which system running the tests is located!
        obs = tester.generate_sample_sheet()
        exp = ('# PI,Dude,test@foo.bar\n'
               '# Contact,Admin,Demo,Shared\n'
               '# Contact emails,admin@foo.bar,demo@microbio.me,'
               'shared@foo.bar\n'
               '[Header]\n'
               'IEMFileVersion,4\n'
               'Investigator Name,Dude\n'
               'Experiment Name,TestExperiment1\n'
               'Date,' + tester_date + '\n'
               'Workflow,GenerateFASTQ\n'
               'Application,FASTQ Only\n'
               'Assay,TruSeq HT\n'
               'Description,\n'
               'Chemistry,Amplicon\n\n'
               '[Reads]\n'
               '151\n'
               '151\n\n'
               '[Settings]\n'
               'ReverseComplement,0\n'
               'Adapter,AGATCGGAAGAGCACACGTCTGAACTCCAGTCA\n'
               'AdapterRead2,AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGT\n\n'
               '[Data]\n'
               'Sample_ID,Sample_Name,Sample_Plate,Sample_Well,I7_Index_ID,'
               'index,I5_Index_ID,index2,Sample_Project,Well_Description,,\n'
               'Test_sequencing_pool_1,,,,,NNNNNNNNNNNN,,,,3080,,,')
        self.assertEqual(obs, exp)

    def test_generate_sample_sheet_amplicon_multiple_lane(self):
        # Amplicon run, multiple lane
        user = User('test@foo.bar')
        tester = SequencingProcess.create(
            user, [PoolComposition(1), PoolComposition(2)], 'TestRun2',
            'TestExperiment2', Equipment(19), 151, 151, user,
            contacts=[User('shared@foo.bar')])
        tester_date = datetime.strftime(tester.date, Process.get_date_format())
        obs = tester.generate_sample_sheet()
        exp = ('# PI,Dude,test@foo.bar\n'
               '# Contact,Shared\n'
               '# Contact emails,shared@foo.bar\n'
               '[Header]\n'
               'IEMFileVersion,4\n'
               'Investigator Name,Dude\n'
               'Experiment Name,TestExperiment2\n'
               'Date,' + tester_date + '\n'
               'Workflow,GenerateFASTQ\n'
               'Application,FASTQ Only\n'
               'Assay,TruSeq HT\n'
               'Description,\n'
               'Chemistry,Amplicon\n\n'
               '[Reads]\n'
               '151\n'
               '151\n\n'
               '[Settings]\n'
               'ReverseComplement,0\n'
               'Adapter,AGATCGGAAGAGCACACGTCTGAACTCCAGTCA\n'
               'AdapterRead2,AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGT\n\n'
               '[Data]\n'
               'Lane,Sample_ID,Sample_Name,Sample_Plate,Sample_Well,I7_Index_'
               'ID,index,I5_Index_ID,index2,Sample_Project,Well_Description,'
               ',\n1,Test_Pool_from_Plate_1,,,,,NNNNNNNNNNNN,,,,3079,,,\n'
               '2,Test_sequencing_pool_1,,,,,NNNNNNNNNNNN,,,,3080,,,')
        self.assertEqual(obs, exp)

    def test_generate_sample_sheet_shotgun(self):
        # Shotgun run
        tester = SequencingProcess(2)
        tester_date = datetime.strftime(tester.date, Process.get_date_format())
        obs = tester.generate_sample_sheet()
        exp = SHOTGUN_SAMPLE_SHEET.format(date=tester_date)
        self.assertEqual(obs, exp)

    def test_generate_amplicon_prep_information(self):
        # Sequencing run
        tester = SequencingProcess(1)
        obs = tester.generate_prep_information()
        exp_key = 'Test Run.1'
        exp = {exp_key: COMBINED_SAMPLES_AMPLICON_PREP_EXAMPLE}
        self.assertEqual(len(obs), len(exp))
        self.assertEqual(obs[exp_key], exp[exp_key])

    def test_generate_metagenomics_prep_information(self):
        tester = SequencingProcess(2)
        obs = tester.generate_prep_information()
        exp_key = 'TestShotgunRun1'
        exp = {exp_key: COMBINED_SAMPLES_METAGENOMICS_PREP_EXAMPLE}

        # extract encoded TSV from dictionaries
        obs = obs['TestShotgunRun1']
        exp = exp['TestShotgunRun1']

        # convert encoded TSVs into lists of rows
        obs = obs.split('\n')
        exp = exp.split('\n')

        # the row order of the expected output is fixed, but the order of the
        # observed output is random. Sorting both lists in place will allow
        # the two outputs to be compared for equality.
        obs.sort()
        exp.sort()

        self.assertListEqual(obs, exp)


# The ordering of positions in this test case recapitulates that provided by
# the wet-lab in known-good examples for plate compression and shotgun library
# prep primer assignment, following an interleaved pattern. See the docstring
# for get_interleaved_quarters_position_generator for more information.
INTERLEAVED_POSITIONS = [
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=0,
                                                    output_col_index=0,
                                                    input_plate_order_index=0,
                                                    input_row_index=0,
                                                    input_col_index=0),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=2,
                                                    output_col_index=0,
                                                    input_plate_order_index=0,
                                                    input_row_index=1,
                                                    input_col_index=0),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=4,
                                                    output_col_index=0,
                                                    input_plate_order_index=0,
                                                    input_row_index=2,
                                                    input_col_index=0),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=6,
                                                    output_col_index=0,
                                                    input_plate_order_index=0,
                                                    input_row_index=3,
                                                    input_col_index=0),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=8,
                                                    output_col_index=0,
                                                    input_plate_order_index=0,
                                                    input_row_index=4,
                                                    input_col_index=0),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=10,
                                                    output_col_index=0,
                                                    input_plate_order_index=0,
                                                    input_row_index=5,
                                                    input_col_index=0),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=12,
                                                    output_col_index=0,
                                                    input_plate_order_index=0,
                                                    input_row_index=6,
                                                    input_col_index=0),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=14,
                                                    output_col_index=0,
                                                    input_plate_order_index=0,
                                                    input_row_index=7,
                                                    input_col_index=0),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=0,
                                                    output_col_index=2,
                                                    input_plate_order_index=0,
                                                    input_row_index=0,
                                                    input_col_index=1),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=2,
                                                    output_col_index=2,
                                                    input_plate_order_index=0,
                                                    input_row_index=1,
                                                    input_col_index=1),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=4,
                                                    output_col_index=2,
                                                    input_plate_order_index=0,
                                                    input_row_index=2,
                                                    input_col_index=1),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=6,
                                                    output_col_index=2,
                                                    input_plate_order_index=0,
                                                    input_row_index=3,
                                                    input_col_index=1),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=8,
                                                    output_col_index=2,
                                                    input_plate_order_index=0,
                                                    input_row_index=4,
                                                    input_col_index=1),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=10,
                                                    output_col_index=2,
                                                    input_plate_order_index=0,
                                                    input_row_index=5,
                                                    input_col_index=1),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=12,
                                                    output_col_index=2,
                                                    input_plate_order_index=0,
                                                    input_row_index=6,
                                                    input_col_index=1),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=14,
                                                    output_col_index=2,
                                                    input_plate_order_index=0,
                                                    input_row_index=7,
                                                    input_col_index=1),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=0,
                                                    output_col_index=4,
                                                    input_plate_order_index=0,
                                                    input_row_index=0,
                                                    input_col_index=2),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=2,
                                                    output_col_index=4,
                                                    input_plate_order_index=0,
                                                    input_row_index=1,
                                                    input_col_index=2),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=4,
                                                    output_col_index=4,
                                                    input_plate_order_index=0,
                                                    input_row_index=2,
                                                    input_col_index=2),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=6,
                                                    output_col_index=4,
                                                    input_plate_order_index=0,
                                                    input_row_index=3,
                                                    input_col_index=2),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=8,
                                                    output_col_index=4,
                                                    input_plate_order_index=0,
                                                    input_row_index=4,
                                                    input_col_index=2),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=10,
                                                    output_col_index=4,
                                                    input_plate_order_index=0,
                                                    input_row_index=5,
                                                    input_col_index=2),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=12,
                                                    output_col_index=4,
                                                    input_plate_order_index=0,
                                                    input_row_index=6,
                                                    input_col_index=2),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=14,
                                                    output_col_index=4,
                                                    input_plate_order_index=0,
                                                    input_row_index=7,
                                                    input_col_index=2),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=0,
                                                    output_col_index=6,
                                                    input_plate_order_index=0,
                                                    input_row_index=0,
                                                    input_col_index=3),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=2,
                                                    output_col_index=6,
                                                    input_plate_order_index=0,
                                                    input_row_index=1,
                                                    input_col_index=3),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=4,
                                                    output_col_index=6,
                                                    input_plate_order_index=0,
                                                    input_row_index=2,
                                                    input_col_index=3),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=6,
                                                    output_col_index=6,
                                                    input_plate_order_index=0,
                                                    input_row_index=3,
                                                    input_col_index=3),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=8,
                                                    output_col_index=6,
                                                    input_plate_order_index=0,
                                                    input_row_index=4,
                                                    input_col_index=3),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=10,
                                                    output_col_index=6,
                                                    input_plate_order_index=0,
                                                    input_row_index=5,
                                                    input_col_index=3),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=12,
                                                    output_col_index=6,
                                                    input_plate_order_index=0,
                                                    input_row_index=6,
                                                    input_col_index=3),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=14,
                                                    output_col_index=6,
                                                    input_plate_order_index=0,
                                                    input_row_index=7,
                                                    input_col_index=3),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=0,
                                                    output_col_index=8,
                                                    input_plate_order_index=0,
                                                    input_row_index=0,
                                                    input_col_index=4),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=2,
                                                    output_col_index=8,
                                                    input_plate_order_index=0,
                                                    input_row_index=1,
                                                    input_col_index=4),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=4,
                                                    output_col_index=8,
                                                    input_plate_order_index=0,
                                                    input_row_index=2,
                                                    input_col_index=4),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=6,
                                                    output_col_index=8,
                                                    input_plate_order_index=0,
                                                    input_row_index=3,
                                                    input_col_index=4),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=8,
                                                    output_col_index=8,
                                                    input_plate_order_index=0,
                                                    input_row_index=4,
                                                    input_col_index=4),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=10,
                                                    output_col_index=8,
                                                    input_plate_order_index=0,
                                                    input_row_index=5,
                                                    input_col_index=4),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=12,
                                                    output_col_index=8,
                                                    input_plate_order_index=0,
                                                    input_row_index=6,
                                                    input_col_index=4),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=14,
                                                    output_col_index=8,
                                                    input_plate_order_index=0,
                                                    input_row_index=7,
                                                    input_col_index=4),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=0,
                                                    output_col_index=10,
                                                    input_plate_order_index=0,
                                                    input_row_index=0,
                                                    input_col_index=5),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=2,
                                                    output_col_index=10,
                                                    input_plate_order_index=0,
                                                    input_row_index=1,
                                                    input_col_index=5),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=4,
                                                    output_col_index=10,
                                                    input_plate_order_index=0,
                                                    input_row_index=2,
                                                    input_col_index=5),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=6,
                                                    output_col_index=10,
                                                    input_plate_order_index=0,
                                                    input_row_index=3,
                                                    input_col_index=5),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=8,
                                                    output_col_index=10,
                                                    input_plate_order_index=0,
                                                    input_row_index=4,
                                                    input_col_index=5),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=10,
                                                    output_col_index=10,
                                                    input_plate_order_index=0,
                                                    input_row_index=5,
                                                    input_col_index=5),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=12,
                                                    output_col_index=10,
                                                    input_plate_order_index=0,
                                                    input_row_index=6,
                                                    input_col_index=5),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=14,
                                                    output_col_index=10,
                                                    input_plate_order_index=0,
                                                    input_row_index=7,
                                                    input_col_index=5),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=0,
                                                    output_col_index=12,
                                                    input_plate_order_index=0,
                                                    input_row_index=0,
                                                    input_col_index=6),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=2,
                                                    output_col_index=12,
                                                    input_plate_order_index=0,
                                                    input_row_index=1,
                                                    input_col_index=6),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=4,
                                                    output_col_index=12,
                                                    input_plate_order_index=0,
                                                    input_row_index=2,
                                                    input_col_index=6),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=6,
                                                    output_col_index=12,
                                                    input_plate_order_index=0,
                                                    input_row_index=3,
                                                    input_col_index=6),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=8,
                                                    output_col_index=12,
                                                    input_plate_order_index=0,
                                                    input_row_index=4,
                                                    input_col_index=6),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=10,
                                                    output_col_index=12,
                                                    input_plate_order_index=0,
                                                    input_row_index=5,
                                                    input_col_index=6),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=12,
                                                    output_col_index=12,
                                                    input_plate_order_index=0,
                                                    input_row_index=6,
                                                    input_col_index=6),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=14,
                                                    output_col_index=12,
                                                    input_plate_order_index=0,
                                                    input_row_index=7,
                                                    input_col_index=6),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=0,
                                                    output_col_index=14,
                                                    input_plate_order_index=0,
                                                    input_row_index=0,
                                                    input_col_index=7),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=2,
                                                    output_col_index=14,
                                                    input_plate_order_index=0,
                                                    input_row_index=1,
                                                    input_col_index=7),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=4,
                                                    output_col_index=14,
                                                    input_plate_order_index=0,
                                                    input_row_index=2,
                                                    input_col_index=7),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=6,
                                                    output_col_index=14,
                                                    input_plate_order_index=0,
                                                    input_row_index=3,
                                                    input_col_index=7),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=8,
                                                    output_col_index=14,
                                                    input_plate_order_index=0,
                                                    input_row_index=4,
                                                    input_col_index=7),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=10,
                                                    output_col_index=14,
                                                    input_plate_order_index=0,
                                                    input_row_index=5,
                                                    input_col_index=7),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=12,
                                                    output_col_index=14,
                                                    input_plate_order_index=0,
                                                    input_row_index=6,
                                                    input_col_index=7),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=14,
                                                    output_col_index=14,
                                                    input_plate_order_index=0,
                                                    input_row_index=7,
                                                    input_col_index=7),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=0,
                                                    output_col_index=16,
                                                    input_plate_order_index=0,
                                                    input_row_index=0,
                                                    input_col_index=8),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=2,
                                                    output_col_index=16,
                                                    input_plate_order_index=0,
                                                    input_row_index=1,
                                                    input_col_index=8),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=4,
                                                    output_col_index=16,
                                                    input_plate_order_index=0,
                                                    input_row_index=2,
                                                    input_col_index=8),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=6,
                                                    output_col_index=16,
                                                    input_plate_order_index=0,
                                                    input_row_index=3,
                                                    input_col_index=8),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=8,
                                                    output_col_index=16,
                                                    input_plate_order_index=0,
                                                    input_row_index=4,
                                                    input_col_index=8),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=10,
                                                    output_col_index=16,
                                                    input_plate_order_index=0,
                                                    input_row_index=5,
                                                    input_col_index=8),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=12,
                                                    output_col_index=16,
                                                    input_plate_order_index=0,
                                                    input_row_index=6,
                                                    input_col_index=8),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=14,
                                                    output_col_index=16,
                                                    input_plate_order_index=0,
                                                    input_row_index=7,
                                                    input_col_index=8),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=0,
                                                    output_col_index=18,
                                                    input_plate_order_index=0,
                                                    input_row_index=0,
                                                    input_col_index=9),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=2,
                                                    output_col_index=18,
                                                    input_plate_order_index=0,
                                                    input_row_index=1,
                                                    input_col_index=9),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=4,
                                                    output_col_index=18,
                                                    input_plate_order_index=0,
                                                    input_row_index=2,
                                                    input_col_index=9),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=6,
                                                    output_col_index=18,
                                                    input_plate_order_index=0,
                                                    input_row_index=3,
                                                    input_col_index=9),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=8,
                                                    output_col_index=18,
                                                    input_plate_order_index=0,
                                                    input_row_index=4,
                                                    input_col_index=9),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=10,
                                                    output_col_index=18,
                                                    input_plate_order_index=0,
                                                    input_row_index=5,
                                                    input_col_index=9),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=12,
                                                    output_col_index=18,
                                                    input_plate_order_index=0,
                                                    input_row_index=6,
                                                    input_col_index=9),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=14,
                                                    output_col_index=18,
                                                    input_plate_order_index=0,
                                                    input_row_index=7,
                                                    input_col_index=9),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=0,
                                                    output_col_index=20,
                                                    input_plate_order_index=0,
                                                    input_row_index=0,
                                                    input_col_index=10),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=2,
                                                    output_col_index=20,
                                                    input_plate_order_index=0,
                                                    input_row_index=1,
                                                    input_col_index=10),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=4,
                                                    output_col_index=20,
                                                    input_plate_order_index=0,
                                                    input_row_index=2,
                                                    input_col_index=10),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=6,
                                                    output_col_index=20,
                                                    input_plate_order_index=0,
                                                    input_row_index=3,
                                                    input_col_index=10),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=8,
                                                    output_col_index=20,
                                                    input_plate_order_index=0,
                                                    input_row_index=4,
                                                    input_col_index=10),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=10,
                                                    output_col_index=20,
                                                    input_plate_order_index=0,
                                                    input_row_index=5,
                                                    input_col_index=10),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=12,
                                                    output_col_index=20,
                                                    input_plate_order_index=0,
                                                    input_row_index=6,
                                                    input_col_index=10),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=14,
                                                    output_col_index=20,
                                                    input_plate_order_index=0,
                                                    input_row_index=7,
                                                    input_col_index=10),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=0,
                                                    output_col_index=22,
                                                    input_plate_order_index=0,
                                                    input_row_index=0,
                                                    input_col_index=11),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=2,
                                                    output_col_index=22,
                                                    input_plate_order_index=0,
                                                    input_row_index=1,
                                                    input_col_index=11),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=4,
                                                    output_col_index=22,
                                                    input_plate_order_index=0,
                                                    input_row_index=2,
                                                    input_col_index=11),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=6,
                                                    output_col_index=22,
                                                    input_plate_order_index=0,
                                                    input_row_index=3,
                                                    input_col_index=11),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=8,
                                                    output_col_index=22,
                                                    input_plate_order_index=0,
                                                    input_row_index=4,
                                                    input_col_index=11),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=10,
                                                    output_col_index=22,
                                                    input_plate_order_index=0,
                                                    input_row_index=5,
                                                    input_col_index=11),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=12,
                                                    output_col_index=22,
                                                    input_plate_order_index=0,
                                                    input_row_index=6,
                                                    input_col_index=11),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=14,
                                                    output_col_index=22,
                                                    input_plate_order_index=0,
                                                    input_row_index=7,
                                                    input_col_index=11),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=0,
                                                    output_col_index=1,
                                                    input_plate_order_index=1,
                                                    input_row_index=0,
                                                    input_col_index=0),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=2,
                                                    output_col_index=1,
                                                    input_plate_order_index=1,
                                                    input_row_index=1,
                                                    input_col_index=0),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=4,
                                                    output_col_index=1,
                                                    input_plate_order_index=1,
                                                    input_row_index=2,
                                                    input_col_index=0),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=6,
                                                    output_col_index=1,
                                                    input_plate_order_index=1,
                                                    input_row_index=3,
                                                    input_col_index=0),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=8,
                                                    output_col_index=1,
                                                    input_plate_order_index=1,
                                                    input_row_index=4,
                                                    input_col_index=0),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=10,
                                                    output_col_index=1,
                                                    input_plate_order_index=1,
                                                    input_row_index=5,
                                                    input_col_index=0),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=12,
                                                    output_col_index=1,
                                                    input_plate_order_index=1,
                                                    input_row_index=6,
                                                    input_col_index=0),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=14,
                                                    output_col_index=1,
                                                    input_plate_order_index=1,
                                                    input_row_index=7,
                                                    input_col_index=0),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=0,
                                                    output_col_index=3,
                                                    input_plate_order_index=1,
                                                    input_row_index=0,
                                                    input_col_index=1),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=2,
                                                    output_col_index=3,
                                                    input_plate_order_index=1,
                                                    input_row_index=1,
                                                    input_col_index=1),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=4,
                                                    output_col_index=3,
                                                    input_plate_order_index=1,
                                                    input_row_index=2,
                                                    input_col_index=1),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=6,
                                                    output_col_index=3,
                                                    input_plate_order_index=1,
                                                    input_row_index=3,
                                                    input_col_index=1),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=8,
                                                    output_col_index=3,
                                                    input_plate_order_index=1,
                                                    input_row_index=4,
                                                    input_col_index=1),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=10,
                                                    output_col_index=3,
                                                    input_plate_order_index=1,
                                                    input_row_index=5,
                                                    input_col_index=1),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=12,
                                                    output_col_index=3,
                                                    input_plate_order_index=1,
                                                    input_row_index=6,
                                                    input_col_index=1),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=14,
                                                    output_col_index=3,
                                                    input_plate_order_index=1,
                                                    input_row_index=7,
                                                    input_col_index=1),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=0,
                                                    output_col_index=5,
                                                    input_plate_order_index=1,
                                                    input_row_index=0,
                                                    input_col_index=2),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=2,
                                                    output_col_index=5,
                                                    input_plate_order_index=1,
                                                    input_row_index=1,
                                                    input_col_index=2),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=4,
                                                    output_col_index=5,
                                                    input_plate_order_index=1,
                                                    input_row_index=2,
                                                    input_col_index=2),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=6,
                                                    output_col_index=5,
                                                    input_plate_order_index=1,
                                                    input_row_index=3,
                                                    input_col_index=2),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=8,
                                                    output_col_index=5,
                                                    input_plate_order_index=1,
                                                    input_row_index=4,
                                                    input_col_index=2),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=10,
                                                    output_col_index=5,
                                                    input_plate_order_index=1,
                                                    input_row_index=5,
                                                    input_col_index=2),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=12,
                                                    output_col_index=5,
                                                    input_plate_order_index=1,
                                                    input_row_index=6,
                                                    input_col_index=2),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=14,
                                                    output_col_index=5,
                                                    input_plate_order_index=1,
                                                    input_row_index=7,
                                                    input_col_index=2),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=0,
                                                    output_col_index=7,
                                                    input_plate_order_index=1,
                                                    input_row_index=0,
                                                    input_col_index=3),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=2,
                                                    output_col_index=7,
                                                    input_plate_order_index=1,
                                                    input_row_index=1,
                                                    input_col_index=3),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=4,
                                                    output_col_index=7,
                                                    input_plate_order_index=1,
                                                    input_row_index=2,
                                                    input_col_index=3),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=6,
                                                    output_col_index=7,
                                                    input_plate_order_index=1,
                                                    input_row_index=3,
                                                    input_col_index=3),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=8,
                                                    output_col_index=7,
                                                    input_plate_order_index=1,
                                                    input_row_index=4,
                                                    input_col_index=3),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=10,
                                                    output_col_index=7,
                                                    input_plate_order_index=1,
                                                    input_row_index=5,
                                                    input_col_index=3),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=12,
                                                    output_col_index=7,
                                                    input_plate_order_index=1,
                                                    input_row_index=6,
                                                    input_col_index=3),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=14,
                                                    output_col_index=7,
                                                    input_plate_order_index=1,
                                                    input_row_index=7,
                                                    input_col_index=3),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=0,
                                                    output_col_index=9,
                                                    input_plate_order_index=1,
                                                    input_row_index=0,
                                                    input_col_index=4),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=2,
                                                    output_col_index=9,
                                                    input_plate_order_index=1,
                                                    input_row_index=1,
                                                    input_col_index=4),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=4,
                                                    output_col_index=9,
                                                    input_plate_order_index=1,
                                                    input_row_index=2,
                                                    input_col_index=4),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=6,
                                                    output_col_index=9,
                                                    input_plate_order_index=1,
                                                    input_row_index=3,
                                                    input_col_index=4),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=8,
                                                    output_col_index=9,
                                                    input_plate_order_index=1,
                                                    input_row_index=4,
                                                    input_col_index=4),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=10,
                                                    output_col_index=9,
                                                    input_plate_order_index=1,
                                                    input_row_index=5,
                                                    input_col_index=4),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=12,
                                                    output_col_index=9,
                                                    input_plate_order_index=1,
                                                    input_row_index=6,
                                                    input_col_index=4),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=14,
                                                    output_col_index=9,
                                                    input_plate_order_index=1,
                                                    input_row_index=7,
                                                    input_col_index=4),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=0,
                                                    output_col_index=11,
                                                    input_plate_order_index=1,
                                                    input_row_index=0,
                                                    input_col_index=5),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=2,
                                                    output_col_index=11,
                                                    input_plate_order_index=1,
                                                    input_row_index=1,
                                                    input_col_index=5),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=4,
                                                    output_col_index=11,
                                                    input_plate_order_index=1,
                                                    input_row_index=2,
                                                    input_col_index=5),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=6,
                                                    output_col_index=11,
                                                    input_plate_order_index=1,
                                                    input_row_index=3,
                                                    input_col_index=5),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=8,
                                                    output_col_index=11,
                                                    input_plate_order_index=1,
                                                    input_row_index=4,
                                                    input_col_index=5),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=10,
                                                    output_col_index=11,
                                                    input_plate_order_index=1,
                                                    input_row_index=5,
                                                    input_col_index=5),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=12,
                                                    output_col_index=11,
                                                    input_plate_order_index=1,
                                                    input_row_index=6,
                                                    input_col_index=5),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=14,
                                                    output_col_index=11,
                                                    input_plate_order_index=1,
                                                    input_row_index=7,
                                                    input_col_index=5),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=0,
                                                    output_col_index=13,
                                                    input_plate_order_index=1,
                                                    input_row_index=0,
                                                    input_col_index=6),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=2,
                                                    output_col_index=13,
                                                    input_plate_order_index=1,
                                                    input_row_index=1,
                                                    input_col_index=6),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=4,
                                                    output_col_index=13,
                                                    input_plate_order_index=1,
                                                    input_row_index=2,
                                                    input_col_index=6),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=6,
                                                    output_col_index=13,
                                                    input_plate_order_index=1,
                                                    input_row_index=3,
                                                    input_col_index=6),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=8,
                                                    output_col_index=13,
                                                    input_plate_order_index=1,
                                                    input_row_index=4,
                                                    input_col_index=6),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=10,
                                                    output_col_index=13,
                                                    input_plate_order_index=1,
                                                    input_row_index=5,
                                                    input_col_index=6),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=12,
                                                    output_col_index=13,
                                                    input_plate_order_index=1,
                                                    input_row_index=6,
                                                    input_col_index=6),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=14,
                                                    output_col_index=13,
                                                    input_plate_order_index=1,
                                                    input_row_index=7,
                                                    input_col_index=6),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=0,
                                                    output_col_index=15,
                                                    input_plate_order_index=1,
                                                    input_row_index=0,
                                                    input_col_index=7),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=2,
                                                    output_col_index=15,
                                                    input_plate_order_index=1,
                                                    input_row_index=1,
                                                    input_col_index=7),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=4,
                                                    output_col_index=15,
                                                    input_plate_order_index=1,
                                                    input_row_index=2,
                                                    input_col_index=7),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=6,
                                                    output_col_index=15,
                                                    input_plate_order_index=1,
                                                    input_row_index=3,
                                                    input_col_index=7),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=8,
                                                    output_col_index=15,
                                                    input_plate_order_index=1,
                                                    input_row_index=4,
                                                    input_col_index=7),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=10,
                                                    output_col_index=15,
                                                    input_plate_order_index=1,
                                                    input_row_index=5,
                                                    input_col_index=7),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=12,
                                                    output_col_index=15,
                                                    input_plate_order_index=1,
                                                    input_row_index=6,
                                                    input_col_index=7),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=14,
                                                    output_col_index=15,
                                                    input_plate_order_index=1,
                                                    input_row_index=7,
                                                    input_col_index=7),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=0,
                                                    output_col_index=17,
                                                    input_plate_order_index=1,
                                                    input_row_index=0,
                                                    input_col_index=8),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=2,
                                                    output_col_index=17,
                                                    input_plate_order_index=1,
                                                    input_row_index=1,
                                                    input_col_index=8),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=4,
                                                    output_col_index=17,
                                                    input_plate_order_index=1,
                                                    input_row_index=2,
                                                    input_col_index=8),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=6,
                                                    output_col_index=17,
                                                    input_plate_order_index=1,
                                                    input_row_index=3,
                                                    input_col_index=8),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=8,
                                                    output_col_index=17,
                                                    input_plate_order_index=1,
                                                    input_row_index=4,
                                                    input_col_index=8),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=10,
                                                    output_col_index=17,
                                                    input_plate_order_index=1,
                                                    input_row_index=5,
                                                    input_col_index=8),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=12,
                                                    output_col_index=17,
                                                    input_plate_order_index=1,
                                                    input_row_index=6,
                                                    input_col_index=8),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=14,
                                                    output_col_index=17,
                                                    input_plate_order_index=1,
                                                    input_row_index=7,
                                                    input_col_index=8),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=0,
                                                    output_col_index=19,
                                                    input_plate_order_index=1,
                                                    input_row_index=0,
                                                    input_col_index=9),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=2,
                                                    output_col_index=19,
                                                    input_plate_order_index=1,
                                                    input_row_index=1,
                                                    input_col_index=9),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=4,
                                                    output_col_index=19,
                                                    input_plate_order_index=1,
                                                    input_row_index=2,
                                                    input_col_index=9),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=6,
                                                    output_col_index=19,
                                                    input_plate_order_index=1,
                                                    input_row_index=3,
                                                    input_col_index=9),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=8,
                                                    output_col_index=19,
                                                    input_plate_order_index=1,
                                                    input_row_index=4,
                                                    input_col_index=9),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=10,
                                                    output_col_index=19,
                                                    input_plate_order_index=1,
                                                    input_row_index=5,
                                                    input_col_index=9),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=12,
                                                    output_col_index=19,
                                                    input_plate_order_index=1,
                                                    input_row_index=6,
                                                    input_col_index=9),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=14,
                                                    output_col_index=19,
                                                    input_plate_order_index=1,
                                                    input_row_index=7,
                                                    input_col_index=9),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=0,
                                                    output_col_index=21,
                                                    input_plate_order_index=1,
                                                    input_row_index=0,
                                                    input_col_index=10),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=2,
                                                    output_col_index=21,
                                                    input_plate_order_index=1,
                                                    input_row_index=1,
                                                    input_col_index=10),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=4,
                                                    output_col_index=21,
                                                    input_plate_order_index=1,
                                                    input_row_index=2,
                                                    input_col_index=10),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=6,
                                                    output_col_index=21,
                                                    input_plate_order_index=1,
                                                    input_row_index=3,
                                                    input_col_index=10),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=8,
                                                    output_col_index=21,
                                                    input_plate_order_index=1,
                                                    input_row_index=4,
                                                    input_col_index=10),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=10,
                                                    output_col_index=21,
                                                    input_plate_order_index=1,
                                                    input_row_index=5,
                                                    input_col_index=10),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=12,
                                                    output_col_index=21,
                                                    input_plate_order_index=1,
                                                    input_row_index=6,
                                                    input_col_index=10),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=14,
                                                    output_col_index=21,
                                                    input_plate_order_index=1,
                                                    input_row_index=7,
                                                    input_col_index=10),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=0,
                                                    output_col_index=23,
                                                    input_plate_order_index=1,
                                                    input_row_index=0,
                                                    input_col_index=11),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=2,
                                                    output_col_index=23,
                                                    input_plate_order_index=1,
                                                    input_row_index=1,
                                                    input_col_index=11),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=4,
                                                    output_col_index=23,
                                                    input_plate_order_index=1,
                                                    input_row_index=2,
                                                    input_col_index=11),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=6,
                                                    output_col_index=23,
                                                    input_plate_order_index=1,
                                                    input_row_index=3,
                                                    input_col_index=11),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=8,
                                                    output_col_index=23,
                                                    input_plate_order_index=1,
                                                    input_row_index=4,
                                                    input_col_index=11),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=10,
                                                    output_col_index=23,
                                                    input_plate_order_index=1,
                                                    input_row_index=5,
                                                    input_col_index=11),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=12,
                                                    output_col_index=23,
                                                    input_plate_order_index=1,
                                                    input_row_index=6,
                                                    input_col_index=11),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=14,
                                                    output_col_index=23,
                                                    input_plate_order_index=1,
                                                    input_row_index=7,
                                                    input_col_index=11),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=1,
                                                    output_col_index=0,
                                                    input_plate_order_index=2,
                                                    input_row_index=0,
                                                    input_col_index=0),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=3,
                                                    output_col_index=0,
                                                    input_plate_order_index=2,
                                                    input_row_index=1,
                                                    input_col_index=0),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=5,
                                                    output_col_index=0,
                                                    input_plate_order_index=2,
                                                    input_row_index=2,
                                                    input_col_index=0),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=7,
                                                    output_col_index=0,
                                                    input_plate_order_index=2,
                                                    input_row_index=3,
                                                    input_col_index=0),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=9,
                                                    output_col_index=0,
                                                    input_plate_order_index=2,
                                                    input_row_index=4,
                                                    input_col_index=0),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=11,
                                                    output_col_index=0,
                                                    input_plate_order_index=2,
                                                    input_row_index=5,
                                                    input_col_index=0),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=13,
                                                    output_col_index=0,
                                                    input_plate_order_index=2,
                                                    input_row_index=6,
                                                    input_col_index=0),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=15,
                                                    output_col_index=0,
                                                    input_plate_order_index=2,
                                                    input_row_index=7,
                                                    input_col_index=0),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=1,
                                                    output_col_index=2,
                                                    input_plate_order_index=2,
                                                    input_row_index=0,
                                                    input_col_index=1),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=3,
                                                    output_col_index=2,
                                                    input_plate_order_index=2,
                                                    input_row_index=1,
                                                    input_col_index=1),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=5,
                                                    output_col_index=2,
                                                    input_plate_order_index=2,
                                                    input_row_index=2,
                                                    input_col_index=1),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=7,
                                                    output_col_index=2,
                                                    input_plate_order_index=2,
                                                    input_row_index=3,
                                                    input_col_index=1),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=9,
                                                    output_col_index=2,
                                                    input_plate_order_index=2,
                                                    input_row_index=4,
                                                    input_col_index=1),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=11,
                                                    output_col_index=2,
                                                    input_plate_order_index=2,
                                                    input_row_index=5,
                                                    input_col_index=1),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=13,
                                                    output_col_index=2,
                                                    input_plate_order_index=2,
                                                    input_row_index=6,
                                                    input_col_index=1),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=15,
                                                    output_col_index=2,
                                                    input_plate_order_index=2,
                                                    input_row_index=7,
                                                    input_col_index=1),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=1,
                                                    output_col_index=4,
                                                    input_plate_order_index=2,
                                                    input_row_index=0,
                                                    input_col_index=2),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=3,
                                                    output_col_index=4,
                                                    input_plate_order_index=2,
                                                    input_row_index=1,
                                                    input_col_index=2),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=5,
                                                    output_col_index=4,
                                                    input_plate_order_index=2,
                                                    input_row_index=2,
                                                    input_col_index=2),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=7,
                                                    output_col_index=4,
                                                    input_plate_order_index=2,
                                                    input_row_index=3,
                                                    input_col_index=2),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=9,
                                                    output_col_index=4,
                                                    input_plate_order_index=2,
                                                    input_row_index=4,
                                                    input_col_index=2),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=11,
                                                    output_col_index=4,
                                                    input_plate_order_index=2,
                                                    input_row_index=5,
                                                    input_col_index=2),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=13,
                                                    output_col_index=4,
                                                    input_plate_order_index=2,
                                                    input_row_index=6,
                                                    input_col_index=2),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=15,
                                                    output_col_index=4,
                                                    input_plate_order_index=2,
                                                    input_row_index=7,
                                                    input_col_index=2),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=1,
                                                    output_col_index=6,
                                                    input_plate_order_index=2,
                                                    input_row_index=0,
                                                    input_col_index=3),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=3,
                                                    output_col_index=6,
                                                    input_plate_order_index=2,
                                                    input_row_index=1,
                                                    input_col_index=3),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=5,
                                                    output_col_index=6,
                                                    input_plate_order_index=2,
                                                    input_row_index=2,
                                                    input_col_index=3),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=7,
                                                    output_col_index=6,
                                                    input_plate_order_index=2,
                                                    input_row_index=3,
                                                    input_col_index=3),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=9,
                                                    output_col_index=6,
                                                    input_plate_order_index=2,
                                                    input_row_index=4,
                                                    input_col_index=3),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=11,
                                                    output_col_index=6,
                                                    input_plate_order_index=2,
                                                    input_row_index=5,
                                                    input_col_index=3),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=13,
                                                    output_col_index=6,
                                                    input_plate_order_index=2,
                                                    input_row_index=6,
                                                    input_col_index=3),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=15,
                                                    output_col_index=6,
                                                    input_plate_order_index=2,
                                                    input_row_index=7,
                                                    input_col_index=3),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=1,
                                                    output_col_index=8,
                                                    input_plate_order_index=2,
                                                    input_row_index=0,
                                                    input_col_index=4),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=3,
                                                    output_col_index=8,
                                                    input_plate_order_index=2,
                                                    input_row_index=1,
                                                    input_col_index=4),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=5,
                                                    output_col_index=8,
                                                    input_plate_order_index=2,
                                                    input_row_index=2,
                                                    input_col_index=4),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=7,
                                                    output_col_index=8,
                                                    input_plate_order_index=2,
                                                    input_row_index=3,
                                                    input_col_index=4),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=9,
                                                    output_col_index=8,
                                                    input_plate_order_index=2,
                                                    input_row_index=4,
                                                    input_col_index=4),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=11,
                                                    output_col_index=8,
                                                    input_plate_order_index=2,
                                                    input_row_index=5,
                                                    input_col_index=4),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=13,
                                                    output_col_index=8,
                                                    input_plate_order_index=2,
                                                    input_row_index=6,
                                                    input_col_index=4),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=15,
                                                    output_col_index=8,
                                                    input_plate_order_index=2,
                                                    input_row_index=7,
                                                    input_col_index=4),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=1,
                                                    output_col_index=10,
                                                    input_plate_order_index=2,
                                                    input_row_index=0,
                                                    input_col_index=5),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=3,
                                                    output_col_index=10,
                                                    input_plate_order_index=2,
                                                    input_row_index=1,
                                                    input_col_index=5),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=5,
                                                    output_col_index=10,
                                                    input_plate_order_index=2,
                                                    input_row_index=2,
                                                    input_col_index=5),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=7,
                                                    output_col_index=10,
                                                    input_plate_order_index=2,
                                                    input_row_index=3,
                                                    input_col_index=5),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=9,
                                                    output_col_index=10,
                                                    input_plate_order_index=2,
                                                    input_row_index=4,
                                                    input_col_index=5),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=11,
                                                    output_col_index=10,
                                                    input_plate_order_index=2,
                                                    input_row_index=5,
                                                    input_col_index=5),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=13,
                                                    output_col_index=10,
                                                    input_plate_order_index=2,
                                                    input_row_index=6,
                                                    input_col_index=5),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=15,
                                                    output_col_index=10,
                                                    input_plate_order_index=2,
                                                    input_row_index=7,
                                                    input_col_index=5),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=1,
                                                    output_col_index=12,
                                                    input_plate_order_index=2,
                                                    input_row_index=0,
                                                    input_col_index=6),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=3,
                                                    output_col_index=12,
                                                    input_plate_order_index=2,
                                                    input_row_index=1,
                                                    input_col_index=6),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=5,
                                                    output_col_index=12,
                                                    input_plate_order_index=2,
                                                    input_row_index=2,
                                                    input_col_index=6),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=7,
                                                    output_col_index=12,
                                                    input_plate_order_index=2,
                                                    input_row_index=3,
                                                    input_col_index=6),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=9,
                                                    output_col_index=12,
                                                    input_plate_order_index=2,
                                                    input_row_index=4,
                                                    input_col_index=6),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=11,
                                                    output_col_index=12,
                                                    input_plate_order_index=2,
                                                    input_row_index=5,
                                                    input_col_index=6),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=13,
                                                    output_col_index=12,
                                                    input_plate_order_index=2,
                                                    input_row_index=6,
                                                    input_col_index=6),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=15,
                                                    output_col_index=12,
                                                    input_plate_order_index=2,
                                                    input_row_index=7,
                                                    input_col_index=6),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=1,
                                                    output_col_index=14,
                                                    input_plate_order_index=2,
                                                    input_row_index=0,
                                                    input_col_index=7),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=3,
                                                    output_col_index=14,
                                                    input_plate_order_index=2,
                                                    input_row_index=1,
                                                    input_col_index=7),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=5,
                                                    output_col_index=14,
                                                    input_plate_order_index=2,
                                                    input_row_index=2,
                                                    input_col_index=7),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=7,
                                                    output_col_index=14,
                                                    input_plate_order_index=2,
                                                    input_row_index=3,
                                                    input_col_index=7),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=9,
                                                    output_col_index=14,
                                                    input_plate_order_index=2,
                                                    input_row_index=4,
                                                    input_col_index=7),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=11,
                                                    output_col_index=14,
                                                    input_plate_order_index=2,
                                                    input_row_index=5,
                                                    input_col_index=7),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=13,
                                                    output_col_index=14,
                                                    input_plate_order_index=2,
                                                    input_row_index=6,
                                                    input_col_index=7),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=15,
                                                    output_col_index=14,
                                                    input_plate_order_index=2,
                                                    input_row_index=7,
                                                    input_col_index=7),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=1,
                                                    output_col_index=16,
                                                    input_plate_order_index=2,
                                                    input_row_index=0,
                                                    input_col_index=8),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=3,
                                                    output_col_index=16,
                                                    input_plate_order_index=2,
                                                    input_row_index=1,
                                                    input_col_index=8),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=5,
                                                    output_col_index=16,
                                                    input_plate_order_index=2,
                                                    input_row_index=2,
                                                    input_col_index=8),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=7,
                                                    output_col_index=16,
                                                    input_plate_order_index=2,
                                                    input_row_index=3,
                                                    input_col_index=8),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=9,
                                                    output_col_index=16,
                                                    input_plate_order_index=2,
                                                    input_row_index=4,
                                                    input_col_index=8),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=11,
                                                    output_col_index=16,
                                                    input_plate_order_index=2,
                                                    input_row_index=5,
                                                    input_col_index=8),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=13,
                                                    output_col_index=16,
                                                    input_plate_order_index=2,
                                                    input_row_index=6,
                                                    input_col_index=8),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=15,
                                                    output_col_index=16,
                                                    input_plate_order_index=2,
                                                    input_row_index=7,
                                                    input_col_index=8),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=1,
                                                    output_col_index=18,
                                                    input_plate_order_index=2,
                                                    input_row_index=0,
                                                    input_col_index=9),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=3,
                                                    output_col_index=18,
                                                    input_plate_order_index=2,
                                                    input_row_index=1,
                                                    input_col_index=9),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=5,
                                                    output_col_index=18,
                                                    input_plate_order_index=2,
                                                    input_row_index=2,
                                                    input_col_index=9),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=7,
                                                    output_col_index=18,
                                                    input_plate_order_index=2,
                                                    input_row_index=3,
                                                    input_col_index=9),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=9,
                                                    output_col_index=18,
                                                    input_plate_order_index=2,
                                                    input_row_index=4,
                                                    input_col_index=9),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=11,
                                                    output_col_index=18,
                                                    input_plate_order_index=2,
                                                    input_row_index=5,
                                                    input_col_index=9),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=13,
                                                    output_col_index=18,
                                                    input_plate_order_index=2,
                                                    input_row_index=6,
                                                    input_col_index=9),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=15,
                                                    output_col_index=18,
                                                    input_plate_order_index=2,
                                                    input_row_index=7,
                                                    input_col_index=9),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=1,
                                                    output_col_index=20,
                                                    input_plate_order_index=2,
                                                    input_row_index=0,
                                                    input_col_index=10),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=3,
                                                    output_col_index=20,
                                                    input_plate_order_index=2,
                                                    input_row_index=1,
                                                    input_col_index=10),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=5,
                                                    output_col_index=20,
                                                    input_plate_order_index=2,
                                                    input_row_index=2,
                                                    input_col_index=10),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=7,
                                                    output_col_index=20,
                                                    input_plate_order_index=2,
                                                    input_row_index=3,
                                                    input_col_index=10),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=9,
                                                    output_col_index=20,
                                                    input_plate_order_index=2,
                                                    input_row_index=4,
                                                    input_col_index=10),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=11,
                                                    output_col_index=20,
                                                    input_plate_order_index=2,
                                                    input_row_index=5,
                                                    input_col_index=10),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=13,
                                                    output_col_index=20,
                                                    input_plate_order_index=2,
                                                    input_row_index=6,
                                                    input_col_index=10),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=15,
                                                    output_col_index=20,
                                                    input_plate_order_index=2,
                                                    input_row_index=7,
                                                    input_col_index=10),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=1,
                                                    output_col_index=22,
                                                    input_plate_order_index=2,
                                                    input_row_index=0,
                                                    input_col_index=11),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=3,
                                                    output_col_index=22,
                                                    input_plate_order_index=2,
                                                    input_row_index=1,
                                                    input_col_index=11),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=5,
                                                    output_col_index=22,
                                                    input_plate_order_index=2,
                                                    input_row_index=2,
                                                    input_col_index=11),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=7,
                                                    output_col_index=22,
                                                    input_plate_order_index=2,
                                                    input_row_index=3,
                                                    input_col_index=11),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=9,
                                                    output_col_index=22,
                                                    input_plate_order_index=2,
                                                    input_row_index=4,
                                                    input_col_index=11),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=11,
                                                    output_col_index=22,
                                                    input_plate_order_index=2,
                                                    input_row_index=5,
                                                    input_col_index=11),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=13,
                                                    output_col_index=22,
                                                    input_plate_order_index=2,
                                                    input_row_index=6,
                                                    input_col_index=11),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=15,
                                                    output_col_index=22,
                                                    input_plate_order_index=2,
                                                    input_row_index=7,
                                                    input_col_index=11),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=1,
                                                    output_col_index=1,
                                                    input_plate_order_index=3,
                                                    input_row_index=0,
                                                    input_col_index=0),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=3,
                                                    output_col_index=1,
                                                    input_plate_order_index=3,
                                                    input_row_index=1,
                                                    input_col_index=0),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=5,
                                                    output_col_index=1,
                                                    input_plate_order_index=3,
                                                    input_row_index=2,
                                                    input_col_index=0),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=7,
                                                    output_col_index=1,
                                                    input_plate_order_index=3,
                                                    input_row_index=3,
                                                    input_col_index=0),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=9,
                                                    output_col_index=1,
                                                    input_plate_order_index=3,
                                                    input_row_index=4,
                                                    input_col_index=0),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=11,
                                                    output_col_index=1,
                                                    input_plate_order_index=3,
                                                    input_row_index=5,
                                                    input_col_index=0),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=13,
                                                    output_col_index=1,
                                                    input_plate_order_index=3,
                                                    input_row_index=6,
                                                    input_col_index=0),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=15,
                                                    output_col_index=1,
                                                    input_plate_order_index=3,
                                                    input_row_index=7,
                                                    input_col_index=0),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=1,
                                                    output_col_index=3,
                                                    input_plate_order_index=3,
                                                    input_row_index=0,
                                                    input_col_index=1),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=3,
                                                    output_col_index=3,
                                                    input_plate_order_index=3,
                                                    input_row_index=1,
                                                    input_col_index=1),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=5,
                                                    output_col_index=3,
                                                    input_plate_order_index=3,
                                                    input_row_index=2,
                                                    input_col_index=1),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=7,
                                                    output_col_index=3,
                                                    input_plate_order_index=3,
                                                    input_row_index=3,
                                                    input_col_index=1),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=9,
                                                    output_col_index=3,
                                                    input_plate_order_index=3,
                                                    input_row_index=4,
                                                    input_col_index=1),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=11,
                                                    output_col_index=3,
                                                    input_plate_order_index=3,
                                                    input_row_index=5,
                                                    input_col_index=1),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=13,
                                                    output_col_index=3,
                                                    input_plate_order_index=3,
                                                    input_row_index=6,
                                                    input_col_index=1),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=15,
                                                    output_col_index=3,
                                                    input_plate_order_index=3,
                                                    input_row_index=7,
                                                    input_col_index=1),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=1,
                                                    output_col_index=5,
                                                    input_plate_order_index=3,
                                                    input_row_index=0,
                                                    input_col_index=2),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=3,
                                                    output_col_index=5,
                                                    input_plate_order_index=3,
                                                    input_row_index=1,
                                                    input_col_index=2),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=5,
                                                    output_col_index=5,
                                                    input_plate_order_index=3,
                                                    input_row_index=2,
                                                    input_col_index=2),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=7,
                                                    output_col_index=5,
                                                    input_plate_order_index=3,
                                                    input_row_index=3,
                                                    input_col_index=2),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=9,
                                                    output_col_index=5,
                                                    input_plate_order_index=3,
                                                    input_row_index=4,
                                                    input_col_index=2),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=11,
                                                    output_col_index=5,
                                                    input_plate_order_index=3,
                                                    input_row_index=5,
                                                    input_col_index=2),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=13,
                                                    output_col_index=5,
                                                    input_plate_order_index=3,
                                                    input_row_index=6,
                                                    input_col_index=2),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=15,
                                                    output_col_index=5,
                                                    input_plate_order_index=3,
                                                    input_row_index=7,
                                                    input_col_index=2),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=1,
                                                    output_col_index=7,
                                                    input_plate_order_index=3,
                                                    input_row_index=0,
                                                    input_col_index=3),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=3,
                                                    output_col_index=7,
                                                    input_plate_order_index=3,
                                                    input_row_index=1,
                                                    input_col_index=3),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=5,
                                                    output_col_index=7,
                                                    input_plate_order_index=3,
                                                    input_row_index=2,
                                                    input_col_index=3),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=7,
                                                    output_col_index=7,
                                                    input_plate_order_index=3,
                                                    input_row_index=3,
                                                    input_col_index=3),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=9,
                                                    output_col_index=7,
                                                    input_plate_order_index=3,
                                                    input_row_index=4,
                                                    input_col_index=3),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=11,
                                                    output_col_index=7,
                                                    input_plate_order_index=3,
                                                    input_row_index=5,
                                                    input_col_index=3),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=13,
                                                    output_col_index=7,
                                                    input_plate_order_index=3,
                                                    input_row_index=6,
                                                    input_col_index=3),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=15,
                                                    output_col_index=7,
                                                    input_plate_order_index=3,
                                                    input_row_index=7,
                                                    input_col_index=3),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=1,
                                                    output_col_index=9,
                                                    input_plate_order_index=3,
                                                    input_row_index=0,
                                                    input_col_index=4),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=3,
                                                    output_col_index=9,
                                                    input_plate_order_index=3,
                                                    input_row_index=1,
                                                    input_col_index=4),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=5,
                                                    output_col_index=9,
                                                    input_plate_order_index=3,
                                                    input_row_index=2,
                                                    input_col_index=4),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=7,
                                                    output_col_index=9,
                                                    input_plate_order_index=3,
                                                    input_row_index=3,
                                                    input_col_index=4),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=9,
                                                    output_col_index=9,
                                                    input_plate_order_index=3,
                                                    input_row_index=4,
                                                    input_col_index=4),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=11,
                                                    output_col_index=9,
                                                    input_plate_order_index=3,
                                                    input_row_index=5,
                                                    input_col_index=4),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=13,
                                                    output_col_index=9,
                                                    input_plate_order_index=3,
                                                    input_row_index=6,
                                                    input_col_index=4),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=15,
                                                    output_col_index=9,
                                                    input_plate_order_index=3,
                                                    input_row_index=7,
                                                    input_col_index=4),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=1,
                                                    output_col_index=11,
                                                    input_plate_order_index=3,
                                                    input_row_index=0,
                                                    input_col_index=5),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=3,
                                                    output_col_index=11,
                                                    input_plate_order_index=3,
                                                    input_row_index=1,
                                                    input_col_index=5),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=5,
                                                    output_col_index=11,
                                                    input_plate_order_index=3,
                                                    input_row_index=2,
                                                    input_col_index=5),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=7,
                                                    output_col_index=11,
                                                    input_plate_order_index=3,
                                                    input_row_index=3,
                                                    input_col_index=5),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=9,
                                                    output_col_index=11,
                                                    input_plate_order_index=3,
                                                    input_row_index=4,
                                                    input_col_index=5),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=11,
                                                    output_col_index=11,
                                                    input_plate_order_index=3,
                                                    input_row_index=5,
                                                    input_col_index=5),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=13,
                                                    output_col_index=11,
                                                    input_plate_order_index=3,
                                                    input_row_index=6,
                                                    input_col_index=5),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=15,
                                                    output_col_index=11,
                                                    input_plate_order_index=3,
                                                    input_row_index=7,
                                                    input_col_index=5),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=1,
                                                    output_col_index=13,
                                                    input_plate_order_index=3,
                                                    input_row_index=0,
                                                    input_col_index=6),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=3,
                                                    output_col_index=13,
                                                    input_plate_order_index=3,
                                                    input_row_index=1,
                                                    input_col_index=6),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=5,
                                                    output_col_index=13,
                                                    input_plate_order_index=3,
                                                    input_row_index=2,
                                                    input_col_index=6),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=7,
                                                    output_col_index=13,
                                                    input_plate_order_index=3,
                                                    input_row_index=3,
                                                    input_col_index=6),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=9,
                                                    output_col_index=13,
                                                    input_plate_order_index=3,
                                                    input_row_index=4,
                                                    input_col_index=6),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=11,
                                                    output_col_index=13,
                                                    input_plate_order_index=3,
                                                    input_row_index=5,
                                                    input_col_index=6),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=13,
                                                    output_col_index=13,
                                                    input_plate_order_index=3,
                                                    input_row_index=6,
                                                    input_col_index=6),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=15,
                                                    output_col_index=13,
                                                    input_plate_order_index=3,
                                                    input_row_index=7,
                                                    input_col_index=6),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=1,
                                                    output_col_index=15,
                                                    input_plate_order_index=3,
                                                    input_row_index=0,
                                                    input_col_index=7),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=3,
                                                    output_col_index=15,
                                                    input_plate_order_index=3,
                                                    input_row_index=1,
                                                    input_col_index=7),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=5,
                                                    output_col_index=15,
                                                    input_plate_order_index=3,
                                                    input_row_index=2,
                                                    input_col_index=7),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=7,
                                                    output_col_index=15,
                                                    input_plate_order_index=3,
                                                    input_row_index=3,
                                                    input_col_index=7),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=9,
                                                    output_col_index=15,
                                                    input_plate_order_index=3,
                                                    input_row_index=4,
                                                    input_col_index=7),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=11,
                                                    output_col_index=15,
                                                    input_plate_order_index=3,
                                                    input_row_index=5,
                                                    input_col_index=7),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=13,
                                                    output_col_index=15,
                                                    input_plate_order_index=3,
                                                    input_row_index=6,
                                                    input_col_index=7),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=15,
                                                    output_col_index=15,
                                                    input_plate_order_index=3,
                                                    input_row_index=7,
                                                    input_col_index=7),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=1,
                                                    output_col_index=17,
                                                    input_plate_order_index=3,
                                                    input_row_index=0,
                                                    input_col_index=8),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=3,
                                                    output_col_index=17,
                                                    input_plate_order_index=3,
                                                    input_row_index=1,
                                                    input_col_index=8),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=5,
                                                    output_col_index=17,
                                                    input_plate_order_index=3,
                                                    input_row_index=2,
                                                    input_col_index=8),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=7,
                                                    output_col_index=17,
                                                    input_plate_order_index=3,
                                                    input_row_index=3,
                                                    input_col_index=8),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=9,
                                                    output_col_index=17,
                                                    input_plate_order_index=3,
                                                    input_row_index=4,
                                                    input_col_index=8),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=11,
                                                    output_col_index=17,
                                                    input_plate_order_index=3,
                                                    input_row_index=5,
                                                    input_col_index=8),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=13,
                                                    output_col_index=17,
                                                    input_plate_order_index=3,
                                                    input_row_index=6,
                                                    input_col_index=8),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=15,
                                                    output_col_index=17,
                                                    input_plate_order_index=3,
                                                    input_row_index=7,
                                                    input_col_index=8),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=1,
                                                    output_col_index=19,
                                                    input_plate_order_index=3,
                                                    input_row_index=0,
                                                    input_col_index=9),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=3,
                                                    output_col_index=19,
                                                    input_plate_order_index=3,
                                                    input_row_index=1,
                                                    input_col_index=9),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=5,
                                                    output_col_index=19,
                                                    input_plate_order_index=3,
                                                    input_row_index=2,
                                                    input_col_index=9),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=7,
                                                    output_col_index=19,
                                                    input_plate_order_index=3,
                                                    input_row_index=3,
                                                    input_col_index=9),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=9,
                                                    output_col_index=19,
                                                    input_plate_order_index=3,
                                                    input_row_index=4,
                                                    input_col_index=9),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=11,
                                                    output_col_index=19,
                                                    input_plate_order_index=3,
                                                    input_row_index=5,
                                                    input_col_index=9),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=13,
                                                    output_col_index=19,
                                                    input_plate_order_index=3,
                                                    input_row_index=6,
                                                    input_col_index=9),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=15,
                                                    output_col_index=19,
                                                    input_plate_order_index=3,
                                                    input_row_index=7,
                                                    input_col_index=9),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=1,
                                                    output_col_index=21,
                                                    input_plate_order_index=3,
                                                    input_row_index=0,
                                                    input_col_index=10),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=3,
                                                    output_col_index=21,
                                                    input_plate_order_index=3,
                                                    input_row_index=1,
                                                    input_col_index=10),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=5,
                                                    output_col_index=21,
                                                    input_plate_order_index=3,
                                                    input_row_index=2,
                                                    input_col_index=10),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=7,
                                                    output_col_index=21,
                                                    input_plate_order_index=3,
                                                    input_row_index=3,
                                                    input_col_index=10),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=9,
                                                    output_col_index=21,
                                                    input_plate_order_index=3,
                                                    input_row_index=4,
                                                    input_col_index=10),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=11,
                                                    output_col_index=21,
                                                    input_plate_order_index=3,
                                                    input_row_index=5,
                                                    input_col_index=10),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=13,
                                                    output_col_index=21,
                                                    input_plate_order_index=3,
                                                    input_row_index=6,
                                                    input_col_index=10),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=15,
                                                    output_col_index=21,
                                                    input_plate_order_index=3,
                                                    input_row_index=7,
                                                    input_col_index=10),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=1,
                                                    output_col_index=23,
                                                    input_plate_order_index=3,
                                                    input_row_index=0,
                                                    input_col_index=11),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=3,
                                                    output_col_index=23,
                                                    input_plate_order_index=3,
                                                    input_row_index=1,
                                                    input_col_index=11),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=5,
                                                    output_col_index=23,
                                                    input_plate_order_index=3,
                                                    input_row_index=2,
                                                    input_col_index=11),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=7,
                                                    output_col_index=23,
                                                    input_plate_order_index=3,
                                                    input_row_index=3,
                                                    input_col_index=11),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=9,
                                                    output_col_index=23,
                                                    input_plate_order_index=3,
                                                    input_row_index=4,
                                                    input_col_index=11),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=11,
                                                    output_col_index=23,
                                                    input_plate_order_index=3,
                                                    input_row_index=5,
                                                    input_col_index=11),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=13,
                                                    output_col_index=23,
                                                    input_plate_order_index=3,
                                                    input_row_index=6,
                                                    input_col_index=11),
    GDNAPlateCompressionProcess.InterleavedPosition(output_row_index=15,
                                                    output_col_index=23,
                                                    input_plate_order_index=3,
                                                    input_row_index=7,
                                                    input_col_index=11)]

SHOTGUN_PRIMER_LAYOUT = [[['A1', 'iTru7_115_09', 'iTru5_121_H'],
                          ['A2', 'iTru7_108_09', 'iTru5_08_H'],
                          ['A3', 'iTru7_101_06', 'iTru5_05_A'],
                          ['A4', 'iTru7_109_05', 'iTru5_16_A'],
                          ['A5', 'iTru7_102_02', 'iTru5_01_B'],
                          ['A6', 'iTru7_110_01', 'iTru5_24_A'],
                          ['A7', 'iTru7_102_10', 'iTru5_09_B'],
                          ['A8', 'iTru7_110_09', 'iTru5_20_B'],
                          ['A9', 'iTru7_103_06', 'iTru5_05_C'],
                          ['A10', 'iTru7_111_05', 'iTru5_16_C'],
                          ['A11', 'iTru7_104_02', 'iTru5_01_D'],
                          ['A12', 'iTru7_112_01', 'iTru5_24_C'],
                          ['A13', 'iTru7_104_10', 'iTru5_09_D'],
                          ['A14', 'iTru7_112_09', 'iTru5_20_D'],
                          ['A15', 'iTru7_105_06', 'iTru5_05_E'],
                          ['A16', 'iTru7_113_05', 'iTru5_16_E'],
                          ['A17', 'iTru7_106_02', 'iTru5_01_F'],
                          ['A18', 'iTru7_114_01', 'iTru5_24_E'],
                          ['A19', 'iTru7_106_10', 'iTru5_09_F'],
                          ['A20', 'iTru7_114_09', 'iTru5_20_F'],
                          ['A21', 'iTru7_107_06', 'iTru5_05_G'],
                          ['A22', 'iTru7_201_05', 'iTru5_16_G'],
                          ['A23', 'iTru7_108_02', 'iTru5_01_H'],
                          ['A24', 'iTru7_202_01', 'iTru5_24_G']],
                         [['B1', 'iTru7_202_08', 'iTru5_19_H'],
                          ['B2', 'iTru7_210_07', 'iTru5_106_H'],
                          ['B3', 'iTru7_203_04', 'iTru5_103_A'],
                          ['B4', 'iTru7_301_03', 'iTru5_114_A'],
                          ['B5', 'iTru7_203_12', 'iTru5_111_A'],
                          ['B6', 'iTru7_301_11', 'iTru5_122_A'],
                          ['B7', 'iTru7_204_08', 'iTru5_107_B'],
                          ['B8', 'iTru7_302_07', 'iTru5_118_B'],
                          ['B9', 'iTru7_205_04', 'iTru5_103_C'],
                          ['B10', 'iTru7_303_03', 'iTru5_114_C'],
                          ['B11', 'iTru7_205_12', 'iTru5_111_C'],
                          ['B12', 'iTru7_303_11', 'iTru5_122_C'],
                          ['B13', 'iTru7_206_08', 'iTru5_107_D'],
                          ['B14', 'iTru7_304_07', 'iTru5_118_D'],
                          ['B15', 'iTru7_207_04', 'iTru5_103_E'],
                          ['B16', 'iTru7_305_03', 'iTru5_114_E'],
                          ['B17', 'iTru7_207_12', 'iTru5_111_E'],
                          ['B18', 'iTru7_305_11', 'iTru5_122_E'],
                          ['B19', 'iTru7_208_08', 'iTru5_107_F'],
                          ['B20', 'iTru7_401_07', 'iTru5_118_F'],
                          ['B21', 'iTru7_209_04', 'iTru5_103_G'],
                          ['B22', 'iTru7_402_03', 'iTru5_114_G'],
                          ['B23', 'iTru7_209_12', 'iTru5_111_G'],
                          ['B24', 'iTru7_402_11', 'iTru5_122_G']],
                         [['C1', 'iTru7_115_10', 'iTru5_122_H'],
                          ['C2', 'iTru7_108_10', 'iTru5_09_H'],
                          ['C3', 'iTru7_101_07', 'iTru5_06_A'],
                          ['C4', 'iTru7_109_06', 'iTru5_17_A'],
                          ['C5', 'iTru7_102_03', 'iTru5_02_B'],
                          ['C6', 'iTru7_110_02', 'iTru5_13_B'],
                          ['C7', 'iTru7_102_11', 'iTru5_10_B'],
                          ['C8', 'iTru7_110_10', 'iTru5_21_B'],
                          ['C9', 'iTru7_103_07', 'iTru5_06_C'],
                          ['C10', 'iTru7_111_06', 'iTru5_17_C'],
                          ['C11', 'iTru7_104_03', 'iTru5_02_D'],
                          ['C12', 'iTru7_112_02', 'iTru5_13_D'],
                          ['C13', 'iTru7_104_11', 'iTru5_10_D'],
                          ['C14', 'iTru7_112_10', 'iTru5_21_D'],
                          ['C15', 'iTru7_105_07', 'iTru5_06_E'],
                          ['C16', 'iTru7_113_06', 'iTru5_17_E'],
                          ['C17', 'iTru7_106_03', 'iTru5_02_F'],
                          ['C18', 'iTru7_114_02', 'iTru5_13_F'],
                          ['C19', 'iTru7_106_11', 'iTru5_10_F'],
                          ['C20', 'iTru7_114_10', 'iTru5_21_F'],
                          ['C21', 'iTru7_107_07', 'iTru5_06_G'],
                          ['C22', 'iTru7_201_06', 'iTru5_17_G'],
                          ['C23', 'iTru7_108_03', 'iTru5_02_H'],
                          ['C24', 'iTru7_202_02', 'iTru5_13_H']],
                         [['D1', 'iTru7_202_09', 'iTru5_20_H'],
                          ['D2', 'iTru7_210_08', 'iTru5_107_H'],
                          ['D3', 'iTru7_203_05', 'iTru5_104_A'],
                          ['D4', 'iTru7_301_04', 'iTru5_115_A'],
                          ['D5', 'iTru7_204_01', 'iTru5_112_A'],
                          ['D6', 'iTru7_301_12', 'iTru5_123_A'],
                          ['D7', 'iTru7_204_09', 'iTru5_108_B'],
                          ['D8', 'iTru7_302_08', 'iTru5_119_B'],
                          ['D9', 'iTru7_205_05', 'iTru5_104_C'],
                          ['D10', 'iTru7_303_04', 'iTru5_115_C'],
                          ['D11', 'iTru7_206_01', 'iTru5_112_C'],
                          ['D12', 'iTru7_303_12', 'iTru5_123_C'],
                          ['D13', 'iTru7_206_09', 'iTru5_108_D'],
                          ['D14', 'iTru7_304_08', 'iTru5_119_D'],
                          ['D15', 'iTru7_207_05', 'iTru5_104_E'],
                          ['D16', 'iTru7_305_04', 'iTru5_115_E'],
                          ['D17', 'iTru7_208_01', 'iTru5_112_E'],
                          ['D18', 'iTru7_305_12', 'iTru5_123_E'],
                          ['D19', 'iTru7_208_09', 'iTru5_108_F'],
                          ['D20', 'iTru7_401_08', 'iTru5_119_F'],
                          ['D21', 'iTru7_209_05', 'iTru5_104_G'],
                          ['D22', 'iTru7_402_04', 'iTru5_115_G'],
                          ['D23', 'iTru7_210_01', 'iTru5_112_G'],
                          ['D24', 'iTru7_402_12', 'iTru5_123_G']],
                         [['E1', 'iTru7_115_11', 'iTru5_123_H'],
                          ['E2', 'iTru7_108_11', 'iTru5_10_H'],
                          ['E3', 'iTru7_101_08', 'iTru5_07_A'],
                          ['E4', 'iTru7_109_07', 'iTru5_18_A'],
                          ['E5', 'iTru7_102_04', 'iTru5_03_B'],
                          ['E6', 'iTru7_110_03', 'iTru5_14_B'],
                          ['E7', 'iTru7_102_12', 'iTru5_11_B'],
                          ['E8', 'iTru7_110_11', 'iTru5_22_B'],
                          ['E9', 'iTru7_103_08', 'iTru5_07_C'],
                          ['E10', 'iTru7_111_07', 'iTru5_18_C'],
                          ['E11', 'iTru7_104_04', 'iTru5_03_D'],
                          ['E12', 'iTru7_112_03', 'iTru5_14_D'],
                          ['E13', 'iTru7_104_12', 'iTru5_11_D'],
                          ['E14', 'iTru7_112_11', 'iTru5_22_D'],
                          ['E15', 'iTru7_105_08', 'iTru5_07_E'],
                          ['E16', 'iTru7_113_07', 'iTru5_18_E'],
                          ['E17', 'iTru7_106_04', 'iTru5_03_F'],
                          ['E18', 'iTru7_114_03', 'iTru5_14_F'],
                          ['E19', 'iTru7_106_12', 'iTru5_11_F'],
                          ['E20', 'iTru7_114_11', 'iTru5_22_F'],
                          ['E21', 'iTru7_107_08', 'iTru5_07_G'],
                          ['E22', 'iTru7_201_07', 'iTru5_18_G'],
                          ['E23', 'iTru7_108_04', 'iTru5_03_H'],
                          ['E24', 'iTru7_202_03', 'iTru5_14_H']],
                         [['F1', 'iTru7_202_10', 'iTru5_21_H'],
                          ['F2', 'iTru7_210_09', 'iTru5_108_H'],
                          ['F3', 'iTru7_203_06', 'iTru5_105_A'],
                          ['F4', 'iTru7_301_05', 'iTru5_116_A'],
                          ['F5', 'iTru7_204_02', 'iTru5_101_B'],
                          ['F6', 'iTru7_302_01', 'iTru5_124_A'],
                          ['F7', 'iTru7_204_10', 'iTru5_109_B'],
                          ['F8', 'iTru7_302_09', 'iTru5_120_B'],
                          ['F9', 'iTru7_205_06', 'iTru5_105_C'],
                          ['F10', 'iTru7_303_05', 'iTru5_116_C'],
                          ['F11', 'iTru7_206_02', 'iTru5_101_D'],
                          ['F12', 'iTru7_304_01', 'iTru5_124_C'],
                          ['F13', 'iTru7_206_10', 'iTru5_109_D'],
                          ['F14', 'iTru7_304_09', 'iTru5_120_D'],
                          ['F15', 'iTru7_207_06', 'iTru5_105_E'],
                          ['F16', 'iTru7_305_05', 'iTru5_116_E'],
                          ['F17', 'iTru7_208_02', 'iTru5_101_F'],
                          ['F18', 'iTru7_401_01', 'iTru5_124_E'],
                          ['F19', 'iTru7_208_10', 'iTru5_109_F'],
                          ['F20', 'iTru7_401_09', 'iTru5_120_F'],
                          ['F21', 'iTru7_209_06', 'iTru5_105_G'],
                          ['F22', 'iTru7_402_05', 'iTru5_116_G'],
                          ['F23', 'iTru7_210_02', 'iTru5_101_H'],
                          ['F24', 'iTru7_115_01', 'iTru5_124_G']],
                         [['G1', 'iTru7_211_01', 'iTru5_124_H'],
                          ['G2', 'iTru7_108_12', 'iTru5_11_H'],
                          ['G3', 'iTru7_101_09', 'iTru5_08_A'],
                          ['G4', 'iTru7_109_08', 'iTru5_19_A'],
                          ['G5', 'iTru7_102_05', 'iTru5_04_B'],
                          ['G6', 'iTru7_110_04', 'iTru5_15_B'],
                          ['G7', 'iTru7_103_01', 'iTru5_12_B'],
                          ['G8', 'iTru7_110_12', 'iTru5_23_B'],
                          ['G9', 'iTru7_103_09', 'iTru5_08_C'],
                          ['G10', 'iTru7_111_08', 'iTru5_19_C'],
                          ['G11', 'iTru7_104_05', 'iTru5_04_D'],
                          ['G12', 'iTru7_112_04', 'iTru5_15_D'],
                          ['G13', 'iTru7_105_01', 'iTru5_12_D'],
                          ['G14', 'iTru7_112_12', 'iTru5_23_D'],
                          ['G15', 'iTru7_105_09', 'iTru5_08_E'],
                          ['G16', 'iTru7_113_08', 'iTru5_19_E'],
                          ['G17', 'iTru7_106_05', 'iTru5_04_F'],
                          ['G18', 'iTru7_114_04', 'iTru5_15_F'],
                          ['G19', 'iTru7_107_01', 'iTru5_12_F'],
                          ['G20', 'iTru7_114_12', 'iTru5_23_F'],
                          ['G21', 'iTru7_107_09', 'iTru5_08_G'],
                          ['G22', 'iTru7_201_08', 'iTru5_19_G'],
                          ['G23', 'iTru7_108_05', 'iTru5_04_H'],
                          ['G24', 'iTru7_202_04', 'iTru5_15_H']],
                         [['H1', 'iTru7_202_11', 'iTru5_22_H'],
                          ['H2', 'iTru7_210_10', 'iTru5_109_H'],
                          ['H3', 'iTru7_203_07', 'iTru5_106_A'],
                          ['H4', 'iTru7_301_06', 'iTru5_117_A'],
                          ['H5', 'iTru7_204_03', 'iTru5_102_B'],
                          ['H6', 'iTru7_302_02', 'iTru5_113_B'],
                          ['H7', 'iTru7_204_11', 'iTru5_110_B'],
                          ['H8', 'iTru7_302_10', 'iTru5_121_B'],
                          ['H9', 'iTru7_205_07', 'iTru5_106_C'],
                          ['H10', 'iTru7_303_06', 'iTru5_117_C'],
                          ['H11', 'iTru7_206_03', 'iTru5_102_D'],
                          ['H12', 'iTru7_304_02', 'iTru5_113_D'],
                          ['H13', 'iTru7_206_11', 'iTru5_110_D'],
                          ['H14', 'iTru7_304_10', 'iTru5_121_D'],
                          ['H15', 'iTru7_207_07', 'iTru5_106_E'],
                          ['H16', 'iTru7_305_06', 'iTru5_117_E'],
                          ['H17', 'iTru7_208_03', 'iTru5_102_F'],
                          ['H18', 'iTru7_401_02', 'iTru5_113_F'],
                          ['H19', 'iTru7_208_11', 'iTru5_110_F'],
                          ['H20', 'iTru7_401_10', 'iTru5_121_F'],
                          ['H21', 'iTru7_209_07', 'iTru5_106_G'],
                          ['H22', 'iTru7_402_06', 'iTru5_117_G'],
                          ['H23', 'iTru7_210_03', 'iTru5_102_H'],
                          ['H24', 'iTru7_115_02', 'iTru5_113_H']],
                         [['I1', 'iTru7_101_02', 'iTru5_01_A'],
                          ['I2', 'iTru7_109_01', 'iTru5_12_H'],
                          ['I3', 'iTru7_101_10', 'iTru5_09_A'],
                          ['I4', 'iTru7_109_09', 'iTru5_20_A'],
                          ['I5', 'iTru7_102_06', 'iTru5_05_B'],
                          ['I6', 'iTru7_110_05', 'iTru5_16_B'],
                          ['I7', 'iTru7_103_02', 'iTru5_01_C'],
                          ['I8', 'iTru7_111_01', 'iTru5_24_B'],
                          ['I9', 'iTru7_103_10', 'iTru5_09_C'],
                          ['I10', 'iTru7_111_09', 'iTru5_20_C'],
                          ['I11', 'iTru7_104_06', 'iTru5_05_D'],
                          ['I12', 'iTru7_112_05', 'iTru5_16_D'],
                          ['I13', 'iTru7_105_02', 'iTru5_01_E'],
                          ['I14', 'iTru7_113_01', 'iTru5_24_D'],
                          ['I15', 'iTru7_105_10', 'iTru5_09_E'],
                          ['I16', 'iTru7_113_09', 'iTru5_20_E'],
                          ['I17', 'iTru7_106_06', 'iTru5_05_F'],
                          ['I18', 'iTru7_114_05', 'iTru5_16_F'],
                          ['I19', 'iTru7_107_02', 'iTru5_01_G'],
                          ['I20', 'iTru7_201_01', 'iTru5_24_F'],
                          ['I21', 'iTru7_107_10', 'iTru5_09_G'],
                          ['I22', 'iTru7_201_09', 'iTru5_20_G'],
                          ['I23', 'iTru7_108_06', 'iTru5_05_H'],
                          ['I24', 'iTru7_202_05', 'iTru5_16_H']],
                         [['J1', 'iTru7_202_12', 'iTru5_23_H'],
                          ['J2', 'iTru7_210_11', 'iTru5_110_H'],
                          ['J3', 'iTru7_203_08', 'iTru5_107_A'],
                          ['J4', 'iTru7_301_07', 'iTru5_118_A'],
                          ['J5', 'iTru7_204_04', 'iTru5_103_B'],
                          ['J6', 'iTru7_302_03', 'iTru5_114_B'],
                          ['J7', 'iTru7_204_12', 'iTru5_111_B'],
                          ['J8', 'iTru7_302_11', 'iTru5_122_B'],
                          ['J9', 'iTru7_205_08', 'iTru5_107_C'],
                          ['J10', 'iTru7_303_07', 'iTru5_118_C'],
                          ['J11', 'iTru7_206_04', 'iTru5_103_D'],
                          ['J12', 'iTru7_304_03', 'iTru5_114_D'],
                          ['J13', 'iTru7_206_12', 'iTru5_111_D'],
                          ['J14', 'iTru7_304_11', 'iTru5_122_D'],
                          ['J15', 'iTru7_207_08', 'iTru5_107_E'],
                          ['J16', 'iTru7_305_07', 'iTru5_118_E'],
                          ['J17', 'iTru7_208_04', 'iTru5_103_F'],
                          ['J18', 'iTru7_401_03', 'iTru5_114_F'],
                          ['J19', 'iTru7_208_12', 'iTru5_111_F'],
                          ['J20', 'iTru7_401_11', 'iTru5_122_F'],
                          ['J21', 'iTru7_209_08', 'iTru5_107_G'],
                          ['J22', 'iTru7_402_07', 'iTru5_118_G'],
                          ['J23', 'iTru7_210_04', 'iTru5_103_H'],
                          ['J24', 'iTru7_115_03', 'iTru5_114_H']],
                         [['K1', 'iTru7_101_03', 'iTru5_02_A'],
                          ['K2', 'iTru7_109_02', 'iTru5_13_A'],
                          ['K3', 'iTru7_101_11', 'iTru5_10_A'],
                          ['K4', 'iTru7_109_10', 'iTru5_21_A'],
                          ['K5', 'iTru7_102_07', 'iTru5_06_B'],
                          ['K6', 'iTru7_110_06', 'iTru5_17_B'],
                          ['K7', 'iTru7_103_03', 'iTru5_02_C'],
                          ['K8', 'iTru7_111_02', 'iTru5_13_C'],
                          ['K9', 'iTru7_103_11', 'iTru5_10_C'],
                          ['K10', 'iTru7_111_10', 'iTru5_21_C'],
                          ['K11', 'iTru7_104_07', 'iTru5_06_D'],
                          ['K12', 'iTru7_112_06', 'iTru5_17_D'],
                          ['K13', 'iTru7_105_03', 'iTru5_02_E'],
                          ['K14', 'iTru7_113_02', 'iTru5_13_E'],
                          ['K15', 'iTru7_105_11', 'iTru5_10_E'],
                          ['K16', 'iTru7_113_10', 'iTru5_21_E'],
                          ['K17', 'iTru7_106_07', 'iTru5_06_F'],
                          ['K18', 'iTru7_114_06', 'iTru5_17_F'],
                          ['K19', 'iTru7_107_03', 'iTru5_02_G'],
                          ['K20', 'iTru7_201_02', 'iTru5_13_G'],
                          ['K21', 'iTru7_107_11', 'iTru5_10_G'],
                          ['K22', 'iTru7_201_10', 'iTru5_21_G'],
                          ['K23', 'iTru7_108_07', 'iTru5_06_H'],
                          ['K24', 'iTru7_202_06', 'iTru5_17_H']],
                         [['L1', 'iTru7_203_01', 'iTru5_24_H'],
                          ['L2', 'iTru7_210_12', 'iTru5_111_H'],
                          ['L3', 'iTru7_203_09', 'iTru5_108_A'],
                          ['L4', 'iTru7_301_08', 'iTru5_119_A'],
                          ['L5', 'iTru7_204_05', 'iTru5_104_B'],
                          ['L6', 'iTru7_302_04', 'iTru5_115_B'],
                          ['L7', 'iTru7_205_01', 'iTru5_112_B'],
                          ['L8', 'iTru7_302_12', 'iTru5_123_B'],
                          ['L9', 'iTru7_205_09', 'iTru5_108_C'],
                          ['L10', 'iTru7_303_08', 'iTru5_119_C'],
                          ['L11', 'iTru7_206_05', 'iTru5_104_D'],
                          ['L12', 'iTru7_304_04', 'iTru5_115_D'],
                          ['L13', 'iTru7_207_01', 'iTru5_112_D'],
                          ['L14', 'iTru7_304_12', 'iTru5_123_D'],
                          ['L15', 'iTru7_207_09', 'iTru5_108_E'],
                          ['L16', 'iTru7_305_08', 'iTru5_119_E'],
                          ['L17', 'iTru7_208_05', 'iTru5_104_F'],
                          ['L18', 'iTru7_401_04', 'iTru5_115_F'],
                          ['L19', 'iTru7_209_01', 'iTru5_112_F'],
                          ['L20', 'iTru7_401_12', 'iTru5_123_F'],
                          ['L21', 'iTru7_209_09', 'iTru5_108_G'],
                          ['L22', 'iTru7_402_08', 'iTru5_119_G'],
                          ['L23', 'iTru7_210_05', 'iTru5_104_H'],
                          ['L24', 'iTru7_115_04', 'iTru5_115_H']],
                         [['M1', 'iTru7_101_04', 'iTru5_03_A'],
                          ['M2', 'iTru7_109_03', 'iTru5_14_A'],
                          ['M3', 'iTru7_101_12', 'iTru5_11_A'],
                          ['M4', 'iTru7_109_11', 'iTru5_22_A'],
                          ['M5', 'iTru7_102_08', 'iTru5_07_B'],
                          ['M6', 'iTru7_110_07', 'iTru5_18_B'],
                          ['M7', 'iTru7_103_04', 'iTru5_03_C'],
                          ['M8', 'iTru7_111_03', 'iTru5_14_C'],
                          ['M9', 'iTru7_103_12', 'iTru5_11_C'],
                          ['M10', 'iTru7_111_11', 'iTru5_22_C'],
                          ['M11', 'iTru7_104_08', 'iTru5_07_D'],
                          ['M12', 'iTru7_112_07', 'iTru5_18_D'],
                          ['M13', 'iTru7_105_04', 'iTru5_03_E'],
                          ['M14', 'iTru7_113_03', 'iTru5_14_E'],
                          ['M15', 'iTru7_105_12', 'iTru5_11_E'],
                          ['M16', 'iTru7_113_11', 'iTru5_22_E'],
                          ['M17', 'iTru7_106_08', 'iTru5_07_F'],
                          ['M18', 'iTru7_114_07', 'iTru5_18_F'],
                          ['M19', 'iTru7_107_04', 'iTru5_03_G'],
                          ['M20', 'iTru7_201_03', 'iTru5_14_G'],
                          ['M21', 'iTru7_107_12', 'iTru5_11_G'],
                          ['M22', 'iTru7_201_11', 'iTru5_22_G'],
                          ['M23', 'iTru7_108_08', 'iTru5_07_H'],
                          ['M24', 'iTru7_202_07', 'iTru5_18_H']],
                         [['N1', 'iTru7_203_02', 'iTru5_101_A'],
                          ['N2', 'iTru7_301_01', 'iTru5_112_H'],
                          ['N3', 'iTru7_203_10', 'iTru5_109_A'],
                          ['N4', 'iTru7_301_09', 'iTru5_120_A'],
                          ['N5', 'iTru7_204_06', 'iTru5_105_B'],
                          ['N6', 'iTru7_302_05', 'iTru5_116_B'],
                          ['N7', 'iTru7_205_02', 'iTru5_101_C'],
                          ['N8', 'iTru7_303_01', 'iTru5_124_B'],
                          ['N9', 'iTru7_205_10', 'iTru5_109_C'],
                          ['N10', 'iTru7_303_09', 'iTru5_120_C'],
                          ['N11', 'iTru7_206_06', 'iTru5_105_D'],
                          ['N12', 'iTru7_304_05', 'iTru5_116_D'],
                          ['N13', 'iTru7_207_02', 'iTru5_101_E'],
                          ['N14', 'iTru7_305_01', 'iTru5_124_D'],
                          ['N15', 'iTru7_207_10', 'iTru5_109_E'],
                          ['N16', 'iTru7_305_09', 'iTru5_120_E'],
                          ['N17', 'iTru7_208_06', 'iTru5_105_F'],
                          ['N18', 'iTru7_401_05', 'iTru5_116_F'],
                          ['N19', 'iTru7_209_02', 'iTru5_101_G'],
                          ['N20', 'iTru7_402_01', 'iTru5_124_F'],
                          ['N21', 'iTru7_209_10', 'iTru5_109_G'],
                          ['N22', 'iTru7_402_09', 'iTru5_120_G'],
                          ['N23', 'iTru7_210_06', 'iTru5_105_H'],
                          ['N24', 'iTru7_115_05', 'iTru5_116_H']],
                         [['O1', 'iTru7_101_05', 'iTru5_04_A'],
                          ['O2', 'iTru7_109_04', 'iTru5_15_A'],
                          ['O3', 'iTru7_102_01', 'iTru5_12_A'],
                          ['O4', 'iTru7_109_12', 'iTru5_23_A'],
                          ['O5', 'iTru7_102_09', 'iTru5_08_B'],
                          ['O6', 'iTru7_110_08', 'iTru5_19_B'],
                          ['O7', 'iTru7_103_05', 'iTru5_04_C'],
                          ['O8', 'iTru7_111_04', 'iTru5_15_C'],
                          ['O9', 'iTru7_104_01', 'iTru5_12_C'],
                          ['O10', 'iTru7_111_12', 'iTru5_23_C'],
                          ['O11', 'iTru7_104_09', 'iTru5_08_D'],
                          ['O12', 'iTru7_112_08', 'iTru5_19_D'],
                          ['O13', 'iTru7_105_05', 'iTru5_04_E'],
                          ['O14', 'iTru7_113_04', 'iTru5_15_E'],
                          ['O15', 'iTru7_106_01', 'iTru5_12_E'],
                          ['O16', 'iTru7_113_12', 'iTru5_23_E'],
                          ['O17', 'iTru7_106_09', 'iTru5_08_F'],
                          ['O18', 'iTru7_114_08', 'iTru5_19_F'],
                          ['O19', 'iTru7_107_05', 'iTru5_04_G'],
                          ['O20', 'iTru7_201_04', 'iTru5_15_G'],
                          ['O21', 'iTru7_108_01', 'iTru5_12_G'],
                          ['O22', 'iTru7_201_12', 'iTru5_23_G'],
                          [None, None, None], [None, None, None]],
                         [['P1', 'iTru7_203_03', 'iTru5_102_A'],
                          ['P2', 'iTru7_301_02', 'iTru5_113_A'],
                          ['P3', 'iTru7_203_11', 'iTru5_110_A'],
                          ['P4', 'iTru7_301_10', 'iTru5_121_A'],
                          ['P5', 'iTru7_204_07', 'iTru5_106_B'],
                          ['P6', 'iTru7_302_06', 'iTru5_117_B'],
                          ['P7', 'iTru7_205_03', 'iTru5_102_C'],
                          ['P8', 'iTru7_303_02', 'iTru5_113_C'],
                          ['P9', 'iTru7_205_11', 'iTru5_110_C'],
                          ['P10', 'iTru7_303_10', 'iTru5_121_C'],
                          ['P11', 'iTru7_206_07', 'iTru5_106_D'],
                          ['P12', 'iTru7_304_06', 'iTru5_117_D'],
                          ['P13', 'iTru7_207_03', 'iTru5_102_E'],
                          ['P14', 'iTru7_305_02', 'iTru5_113_E'],
                          ['P15', 'iTru7_207_11', 'iTru5_110_E'],
                          ['P16', 'iTru7_305_10', 'iTru5_121_E'],
                          ['P17', 'iTru7_208_07', 'iTru5_106_F'],
                          ['P18', 'iTru7_401_06', 'iTru5_117_F'],
                          ['P19', 'iTru7_209_03', 'iTru5_102_G'],
                          ['P20', 'iTru7_402_02', 'iTru5_113_G'],
                          ['P21', 'iTru7_209_11', 'iTru5_110_G'],
                          ['P22', 'iTru7_402_10', 'iTru5_121_G'],
                          [None, None, None], [None, None, None]]]


if __name__ == '__main__':
    main()
