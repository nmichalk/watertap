#################################################################################
# WaterTAP Copyright (c) 2020-2023, The Regents of the University of California,
# through Lawrence Berkeley National Laboratory, Oak Ridge National Laboratory,
# National Renewable Energy Laboratory, and National Energy Technology
# Laboratory (subject to receipt of any required approvals from the U.S. Dept.
# of Energy). All rights reserved.
#
# Please see the files COPYRIGHT.md and LICENSE.md for full copyright and license
# information, respectively. These files are also available online at the URL
# "https://github.com/watertap-org/watertap/"
#################################################################################
"""
Tests for CSTR unit model.
Authors: Marcus Holly
"""

import pytest

from pyomo.environ import (
    assert_optimal_termination,
    check_optimal_termination,
    ConcreteModel,
    units,
    value,
    Objective,
)
from pyomo.util.check_units import assert_units_consistent, assert_units_equivalent

from idaes.core import (
    FlowsheetBlock,
    MaterialBalanceType,
    EnergyBalanceType,
    MomentumBalanceType,
    UnitModelCostingBlock,
)
from watertap.unit_models.cstr import CSTR
from watertap.costing import WaterTAPCosting

from watertap.property_models.activated_sludge.asm1_properties import ASM1ParameterBlock
from watertap.property_models.activated_sludge.asm1_reactions import (
    ASM1ReactionParameterBlock,
)

from idaes.models.properties.examples.saponification_thermo import (
    SaponificationParameterBlock,
)
from idaes.models.properties.examples.saponification_reactions import (
    SaponificationReactionParameterBlock,
)
from idaes.core.util.model_statistics import (
    degrees_of_freedom,
    number_variables,
    number_total_constraints,
    number_unused_variables,
)
from idaes.core.util.testing import (
    PhysicalParameterTestBlock,
    ReactionParameterTestBlock,
    initialization_tester,
)
from idaes.core.solvers import get_solver
from idaes.core.initialization import (
    BlockTriangularizationInitializer,
    SingleControlVolumeUnitInitializer,
    InitializationStatus,
)

# -----------------------------------------------------------------------------
# Get default solver for testing
solver = get_solver()


# -----------------------------------------------------------------------------
@pytest.mark.unit
def test_config():
    m = ConcreteModel()
    m.fs = FlowsheetBlock(dynamic=False)

    m.fs.properties = PhysicalParameterTestBlock()
    m.fs.reactions = ReactionParameterTestBlock(property_package=m.fs.properties)

    m.fs.unit = CSTR(property_package=m.fs.properties, reaction_package=m.fs.reactions)

    # Check unit config arguments
    assert len(m.fs.unit.config) == 14

    assert m.fs.unit.config.material_balance_type == MaterialBalanceType.useDefault
    assert m.fs.unit.config.energy_balance_type == EnergyBalanceType.useDefault
    assert m.fs.unit.config.momentum_balance_type == MomentumBalanceType.pressureTotal
    assert not m.fs.unit.config.has_heat_transfer
    assert not m.fs.unit.config.has_pressure_change
    assert not m.fs.unit.config.has_equilibrium_reactions
    assert not m.fs.unit.config.has_phase_equilibrium
    assert not m.fs.unit.config.has_heat_of_reaction
    assert m.fs.unit.config.property_package is m.fs.properties
    assert m.fs.unit.config.reaction_package is m.fs.reactions

    assert m.fs.unit.default_initializer is SingleControlVolumeUnitInitializer


# -----------------------------------------------------------------------------
class TestSaponification(object):
    @pytest.fixture(scope="class")
    def sapon(self):
        m = ConcreteModel()
        m.fs = FlowsheetBlock(dynamic=False)

        m.fs.properties = SaponificationParameterBlock()
        m.fs.reactions = SaponificationReactionParameterBlock(
            property_package=m.fs.properties
        )

        m.fs.unit = CSTR(
            property_package=m.fs.properties,
            reaction_package=m.fs.reactions,
            has_equilibrium_reactions=False,
            has_heat_transfer=True,
            has_heat_of_reaction=True,
            has_pressure_change=True,
        )

        m.fs.unit.inlet.flow_vol.fix(1.0e-03)
        m.fs.unit.inlet.conc_mol_comp[0, "H2O"].fix(55388.0)
        m.fs.unit.inlet.conc_mol_comp[0, "NaOH"].fix(100.0)
        m.fs.unit.inlet.conc_mol_comp[0, "EthylAcetate"].fix(100.0)
        m.fs.unit.inlet.conc_mol_comp[0, "SodiumAcetate"].fix(0.0)
        m.fs.unit.inlet.conc_mol_comp[0, "Ethanol"].fix(0.0)

        m.fs.unit.inlet.temperature.fix(303.15)
        m.fs.unit.inlet.pressure.fix(101325.0)

        m.fs.unit.volume.fix(1.5e-03)
        m.fs.unit.heat_duty.fix(0)
        m.fs.unit.deltaP.fix(0)

        return m

    @pytest.mark.build
    @pytest.mark.unit
    def test_build(self, sapon):

        assert hasattr(sapon.fs.unit, "inlet")
        assert len(sapon.fs.unit.inlet.vars) == 4
        assert hasattr(sapon.fs.unit.inlet, "flow_vol")
        assert hasattr(sapon.fs.unit.inlet, "conc_mol_comp")
        assert hasattr(sapon.fs.unit.inlet, "temperature")
        assert hasattr(sapon.fs.unit.inlet, "pressure")

        assert hasattr(sapon.fs.unit, "outlet")
        assert len(sapon.fs.unit.outlet.vars) == 4
        assert hasattr(sapon.fs.unit.outlet, "flow_vol")
        assert hasattr(sapon.fs.unit.outlet, "conc_mol_comp")
        assert hasattr(sapon.fs.unit.outlet, "temperature")
        assert hasattr(sapon.fs.unit.outlet, "pressure")

        assert hasattr(sapon.fs.unit, "cstr_performance_eqn")
        assert hasattr(sapon.fs.unit, "volume")
        assert hasattr(sapon.fs.unit, "heat_duty")
        assert hasattr(sapon.fs.unit, "deltaP")

        assert number_variables(sapon) == 28
        assert number_total_constraints(sapon) == 17
        assert number_unused_variables(sapon) == 0

    @pytest.mark.component
    def test_units(self, sapon):
        assert_units_consistent(sapon)
        assert_units_equivalent(sapon.fs.unit.volume[0], units.m**3)
        assert_units_equivalent(sapon.fs.unit.heat_duty[0], units.W)
        assert_units_equivalent(sapon.fs.unit.deltaP[0], units.Pa)

    @pytest.mark.unit
    def test_dof(self, sapon):
        assert degrees_of_freedom(sapon) == 0

    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    @pytest.mark.component
    def test_initialize(self, sapon):
        initialization_tester(sapon)

    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    @pytest.mark.component
    def test_solve(self, sapon):
        results = solver.solve(sapon)

        # Check for optimal solution
        assert check_optimal_termination(results)

    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    @pytest.mark.component
    def test_solution(self, sapon):
        assert pytest.approx(101325.0, abs=1e-2) == value(
            sapon.fs.unit.outlet.pressure[0]
        )
        assert pytest.approx(304.09, abs=1e-2) == value(
            sapon.fs.unit.outlet.temperature[0]
        )
        assert pytest.approx(20.32, abs=1e-2) == value(
            sapon.fs.unit.outlet.conc_mol_comp[0, "EthylAcetate"]
        )

    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    @pytest.mark.component
    def test_conservation(self, sapon):
        assert (
            abs(
                value(
                    sapon.fs.unit.inlet.flow_vol[0] - sapon.fs.unit.outlet.flow_vol[0]
                )
            )
            <= 1e-6
        )
        assert (
            abs(
                value(
                    sapon.fs.unit.inlet.flow_vol[0]
                    * sum(
                        sapon.fs.unit.inlet.conc_mol_comp[0, j]
                        for j in sapon.fs.properties.component_list
                    )
                    - sapon.fs.unit.outlet.flow_vol[0]
                    * sum(
                        sapon.fs.unit.outlet.conc_mol_comp[0, j]
                        for j in sapon.fs.properties.component_list
                    )
                )
            )
            <= 1e-6
        )

        assert pytest.approx(3904.51, abs=1e-2) == value(
            sapon.fs.unit.control_volume.heat_of_reaction[0]
        )
        assert (
            abs(
                value(
                    (
                        sapon.fs.unit.inlet.flow_vol[0]
                        * sapon.fs.properties.dens_mol
                        * sapon.fs.properties.cp_mol
                        * (
                            sapon.fs.unit.inlet.temperature[0]
                            - sapon.fs.properties.temperature_ref
                        )
                    )
                    - (
                        sapon.fs.unit.outlet.flow_vol[0]
                        * sapon.fs.properties.dens_mol
                        * sapon.fs.properties.cp_mol
                        * (
                            sapon.fs.unit.outlet.temperature[0]
                            - sapon.fs.properties.temperature_ref
                        )
                    )
                    + sapon.fs.unit.control_volume.heat_of_reaction[0]
                )
            )
            <= 1e-3
        )

    @pytest.mark.ui
    @pytest.mark.unit
    def test_get_performance_contents(self, sapon):
        perf_dict = sapon.fs.unit._get_performance_contents()

        assert perf_dict == {
            "vars": {
                "Volume": sapon.fs.unit.volume[0],
                "Heat Duty": sapon.fs.unit.heat_duty[0],
                "Pressure Change": sapon.fs.unit.deltaP[0],
            }
        }


class TestInitializers:
    @pytest.fixture
    def model(self):
        m = ConcreteModel()
        m.fs = FlowsheetBlock(dynamic=False)

        m.fs.properties = SaponificationParameterBlock()
        m.fs.reactions = SaponificationReactionParameterBlock(
            property_package=m.fs.properties
        )

        m.fs.unit = CSTR(
            property_package=m.fs.properties,
            reaction_package=m.fs.reactions,
            has_equilibrium_reactions=False,
            has_heat_transfer=True,
            has_heat_of_reaction=True,
            has_pressure_change=True,
        )

        m.fs.unit.inlet.flow_vol[0].set_value(1.0e-03)
        m.fs.unit.inlet.conc_mol_comp[0, "H2O"].set_value(55388.0)
        m.fs.unit.inlet.conc_mol_comp[0, "NaOH"].set_value(100.0)
        m.fs.unit.inlet.conc_mol_comp[0, "EthylAcetate"].set_value(100.0)
        m.fs.unit.inlet.conc_mol_comp[0, "SodiumAcetate"].set_value(0.0)
        m.fs.unit.inlet.conc_mol_comp[0, "Ethanol"].set_value(0.0)

        m.fs.unit.inlet.temperature[0].set_value(303.15)
        m.fs.unit.inlet.pressure[0].set_value(101325.0)

        m.fs.unit.volume[0].fix(1.5e-03)
        m.fs.unit.heat_duty[0].fix(0)
        m.fs.unit.deltaP[0].fix(0)

        return m

    @pytest.mark.component
    def test_general_hierarchical(self, model):
        initializer = SingleControlVolumeUnitInitializer()
        initializer.initialize(model.fs.unit)

        assert initializer.summary[model.fs.unit]["status"] == InitializationStatus.Ok

        assert value(model.fs.unit.outlet.flow_vol[0]) == pytest.approx(1e-3, rel=1e-5)
        assert value(model.fs.unit.outlet.conc_mol_comp[0, "H2O"]) == pytest.approx(
            55388, rel=1e-5
        )
        assert value(model.fs.unit.outlet.conc_mol_comp[0, "NaOH"]) == pytest.approx(
            20.31609, rel=1e-5
        )
        assert value(
            model.fs.unit.outlet.conc_mol_comp[0, "EthylAcetate"]
        ) == pytest.approx(20.31609, rel=1e-5)
        assert value(
            model.fs.unit.outlet.conc_mol_comp[0, "SodiumAcetate"]
        ) == pytest.approx(79.683910, rel=1e-5)
        assert value(model.fs.unit.outlet.conc_mol_comp[0, "Ethanol"]) == pytest.approx(
            79.683910, rel=1e-5
        )
        assert value(model.fs.unit.outlet.temperature[0]) == pytest.approx(
            304.0856, rel=1e-5
        )
        assert value(model.fs.unit.outlet.pressure[0]) == pytest.approx(
            101325, rel=1e-5
        )

        assert not model.fs.unit.inlet.flow_vol[0].fixed
        assert not model.fs.unit.inlet.conc_mol_comp[0, "H2O"].fixed
        assert not model.fs.unit.inlet.conc_mol_comp[0, "NaOH"].fixed
        assert not model.fs.unit.inlet.conc_mol_comp[0, "EthylAcetate"].fixed
        assert not model.fs.unit.inlet.conc_mol_comp[0, "SodiumAcetate"].fixed
        assert not model.fs.unit.inlet.conc_mol_comp[0, "Ethanol"].fixed

        assert not model.fs.unit.inlet.temperature[0].fixed
        assert not model.fs.unit.inlet.pressure[0].fixed

    @pytest.mark.component
    def test_block_triangularization(self, model):
        initializer = BlockTriangularizationInitializer(constraint_tolerance=2e-5)
        initializer.initialize(model.fs.unit)

        assert initializer.summary[model.fs.unit]["status"] == InitializationStatus.Ok

        assert value(model.fs.unit.outlet.flow_vol[0]) == pytest.approx(1e-3, rel=1e-5)
        assert value(model.fs.unit.outlet.conc_mol_comp[0, "H2O"]) == pytest.approx(
            55388, rel=1e-5
        )
        assert value(model.fs.unit.outlet.conc_mol_comp[0, "NaOH"]) == pytest.approx(
            20.31609, rel=1e-5
        )
        assert value(
            model.fs.unit.outlet.conc_mol_comp[0, "EthylAcetate"]
        ) == pytest.approx(20.31609, rel=1e-5)
        assert value(
            model.fs.unit.outlet.conc_mol_comp[0, "SodiumAcetate"]
        ) == pytest.approx(79.683910, rel=1e-5)
        assert value(model.fs.unit.outlet.conc_mol_comp[0, "Ethanol"]) == pytest.approx(
            79.683910, rel=1e-5
        )
        assert value(model.fs.unit.outlet.temperature[0]) == pytest.approx(
            304.0856, rel=1e-5
        )
        assert value(model.fs.unit.outlet.pressure[0]) == pytest.approx(
            101325, rel=1e-5
        )

        assert not model.fs.unit.inlet.flow_vol[0].fixed
        assert not model.fs.unit.inlet.conc_mol_comp[0, "H2O"].fixed
        assert not model.fs.unit.inlet.conc_mol_comp[0, "NaOH"].fixed
        assert not model.fs.unit.inlet.conc_mol_comp[0, "EthylAcetate"].fixed
        assert not model.fs.unit.inlet.conc_mol_comp[0, "SodiumAcetate"].fixed
        assert not model.fs.unit.inlet.conc_mol_comp[0, "Ethanol"].fixed

        assert not model.fs.unit.inlet.temperature[0].fixed
        assert not model.fs.unit.inlet.pressure[0].fixed

    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    @pytest.mark.component
    def test_costing(self):
        m = ConcreteModel()
        m.fs = FlowsheetBlock(dynamic=False)

        m.fs.props_ASM1 = ASM1ParameterBlock()
        m.fs.ASM1_rxn_props = ASM1ReactionParameterBlock(
            property_package=m.fs.props_ASM1
        )

        m.fs.unit = CSTR(
            property_package=m.fs.props_ASM1, reaction_package=m.fs.ASM1_rxn_props
        )

        m.fs.unit.inlet.flow_vol[0].set_value(1.2199 * units.m**3 / units.s)
        m.fs.unit.inlet.alkalinity[0].set_value(4.5102 * units.mole / units.m**3)
        m.fs.unit.inlet.conc_mass_comp[0, "S_I"].set_value(
            0.061909 * units.kg / units.m**3
        )
        m.fs.unit.inlet.conc_mass_comp[0, "S_S"].set_value(
            0.012366 * units.kg / units.m**3
        )
        m.fs.unit.inlet.conc_mass_comp[0, "X_I"].set_value(
            1.4258 * units.kg / units.m**3
        )
        m.fs.unit.inlet.conc_mass_comp[0, "X_S"].set_value(
            0.090508 * units.kg / units.m**3
        )
        m.fs.unit.inlet.conc_mass_comp[0, "X_BH"].set_value(
            2.8404 * units.kg / units.m**3
        )
        m.fs.unit.inlet.conc_mass_comp[0, "X_BA"].set_value(
            0.20512 * units.kg / units.m**3
        )
        m.fs.unit.inlet.conc_mass_comp[0, "X_P"].set_value(
            0.58681 * units.kg / units.m**3
        )
        m.fs.unit.inlet.conc_mass_comp[0, "S_O"].set_value(
            0.00036092 * units.kg / units.m**3
        )
        m.fs.unit.inlet.conc_mass_comp[0, "S_NO"].set_value(
            0.012424 * units.kg / units.m**3
        )
        m.fs.unit.inlet.conc_mass_comp[0, "S_NH"].set_value(
            0.0076936 * units.kg / units.m**3
        )
        m.fs.unit.inlet.conc_mass_comp[0, "S_ND"].set_value(
            0.0019068 * units.kg / units.m**3
        )
        m.fs.unit.inlet.conc_mass_comp[0, "X_ND"].set_value(
            0.0053166 * units.kg / units.m**3
        )

        m.fs.unit.inlet.temperature[0].set_value(308.15 * units.K)
        m.fs.unit.inlet.pressure[0].set_value(84790.0 * units.Pa)

        m.fs.unit.volume[0].fix(1000 * units.m**3)

        m.fs.costing = WaterTAPCosting()

        m.fs.unit.costing = UnitModelCostingBlock(flowsheet_costing_block=m.fs.costing)
        m.fs.costing.cost_process()
        m.fs.costing.add_LCOW(m.fs.unit.control_volume.properties_out[0].flow_vol)
        m.fs.costing.initialize()
        m.objective = Objective(expr=m.fs.costing.LCOW)
        assert_units_consistent(m)
        results = solver.solve(m, tee=True)

        assert_optimal_termination(results)

        # Check solutions
        assert pytest.approx(526.45 * 2, rel=1e-5) == value(
            m.fs.unit.costing.capital_cost
        )
        assert pytest.approx(8.95257e-07, rel=1e-5) == value(m.fs.costing.LCOW)

    @pytest.mark.unit
    def test_report(self, model):
        m = model
        m.fs.unit.report()
