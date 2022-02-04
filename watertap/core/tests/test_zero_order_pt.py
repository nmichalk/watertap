###############################################################################
# WaterTAP Copyright (c) 2021, The Regents of the University of California,
# through Lawrence Berkeley National Laboratory, Oak Ridge National
# Laboratory, National Renewable Energy Laboratory, and National Energy
# Technology Laboratory (subject to receipt of any required approvals from
# the U.S. Dept. of Energy). All rights reserved.
#
# Please see the files COPYRIGHT.md and LICENSE.md for full copyright and license
# information, respectively. These files are also available online at the URL
# "https://github.com/watertap-org/watertap/"
#
###############################################################################
"""
Tests for general zero-order property package
"""
import pytest

from idaes.core import declare_process_block_class, FlowsheetBlock
from idaes.core.util.model_statistics import degrees_of_freedom
from idaes.core.util import get_solver
from pyomo.environ import (ConcreteModel,
                           value)
from pyomo.network import Port
from pyomo.util.check_units import assert_units_consistent

from watertap.core import WaterParameterBlock, WaterStateBlock, ZeroOrderBaseData
from watertap.core.zero_order_pt import (
    build_pt, initialize_pt, calculate_scaling_factors_pt, _get_Q_pt)

solver = get_solver()


@declare_process_block_class("DerivedPT")
class DerivedPTData(ZeroOrderBaseData):
    def build(self):
        super().build()

        build_pt(self)


class TestPT:
    @pytest.fixture(scope="module")
    def model(self):
        m = ConcreteModel()

        m.fs = FlowsheetBlock(default={"dynamic": False})

        m.fs.water_props = WaterParameterBlock(
            default={"solute_list": ["A", "B", "C"]})

        m.fs.unit = DerivedPT(
            default={"property_package": m.fs.water_props})

        m.fs.unit.inlet.flow_vol.fix(42)
        m.fs.unit.inlet.conc_mass_comp[0, "A"].fix(10)
        m.fs.unit.inlet.conc_mass_comp[0, "B"].fix(20)
        m.fs.unit.inlet.conc_mass_comp[0, "C"].fix(30)

        return m

    @pytest.mark.unit
    def test_private_attributes(self, model):
        assert model.fs.unit._tech_type is None
        assert model.fs.unit._has_recovery_removal is False
        assert model.fs.unit._fixed_perf_vars == []
        assert model.fs.unit._initialize is initialize_pt
        assert model.fs.unit._scaling is calculate_scaling_factors_pt
        assert model.fs.unit._get_Q is _get_Q_pt
        assert model.fs.unit._stream_table_dict == {
            "Inlet": model.fs.unit.inlet,
            "Outlet": model.fs.unit.outlet}
        assert model.fs.unit._perf_var_dict == {}

    @pytest.mark.unit
    def test_build(self, model):
        assert isinstance(model.fs.unit.properties, WaterStateBlock)

        assert isinstance(model.fs.unit.inlet, Port)
        assert isinstance(model.fs.unit.outlet, Port)

    @pytest.mark.unit
    def test_degrees_of_freedom(self, model):
        assert degrees_of_freedom(model) == 0

    @pytest.mark.component
    def test_unit_consistency(self, model):
        assert_units_consistent(model)

    # Nothing to initialize or solve

    @pytest.mark.component
    def test_solution(self, model):
        assert (pytest.approx(value(
            model.fs.unit.inlet.flow_vol[0]), rel=1e-5) ==
            value(model.fs.unit.outlet.flow_vol[0]))

        assert (pytest.approx(value(
            model.fs.unit.inlet.conc_mass_comp[0, "A"]), rel=1e-5) ==
            value(model.fs.unit.outlet.conc_mass_comp[0, "A"]))
        assert (pytest.approx(value(
            model.fs.unit.inlet.conc_mass_comp[0, "B"]), rel=1e-5) ==
            value(model.fs.unit.outlet.conc_mass_comp[0, "B"]))
        assert (pytest.approx(value(
            model.fs.unit.inlet.conc_mass_comp[0, "C"]), rel=1e-5) ==
            value(model.fs.unit.outlet.conc_mass_comp[0, "C"]))

    @pytest.mark.component
    def test_report(self, model, capsys):
        model.fs.unit.report()

        output = """
====================================================================================
Unit : fs.unit                                                             Time: 0.0
------------------------------------------------------------------------------------
    Unit Performance


------------------------------------------------------------------------------------
    Stream Table
                          Inlet  Outlet
    Volumetric Flowrate    42      42  
    Mass Concentration A   10      10  
    Mass Concentration B   20      20  
    Mass Concentration C   30      30  
====================================================================================
"""

        captured = capsys.readouterr()
        assert output in captured.out