import fastscapelib_fortran as fs
import numpy as np
import xsimlab as xs

from .context import FastscapelibContext
from .flow import FlowAccumulator, FlowRouter
from .grid import UniformRectilinearGrid2D
from .surface import UniformSoilLayer


@xs.process
class StreamPowerChannel:
    """Stream-Power channel erosion."""

    k_coef = xs.variable(
        dims=[(), ('y', 'x')],
        description='bedrock channel incision coefficient'
    )
    area_exp = xs.variable(description='drainage area exponent')
    slope_exp = xs.variable(description='slope exponent')

    shape = xs.foreign(UniformRectilinearGrid2D, 'shape')
    elevation = xs.foreign(FlowRouter, 'elevation')
    receivers = xs.foreign(FlowRouter, 'receivers')
    flowacc = xs.foreign(FlowAccumulator, 'flowacc')
    fs_context = xs.foreign(FastscapelibContext, 'context')

    erosion = xs.variable(dims=('y', 'x'), intent='out', group='erosion')

    chi = xs.on_demand(
        dims=('y', 'x'),
        description='integrated drainage area (chi)'
    )

    def _set_g_in_context(self):
        # transport/deposition feature is exposed in subclasses
        self.fs_context.g1 = 0.
        self.fs_context.g2 = -1.

    def run_step(self):
        kf = np.broadcast_to(self.k_coef, self.shape).flatten()
        self.fs_context.kf = kf

        # we don't use kfsed fastscapelib-fortran feature directly
        self.fs_context.kfsed = -1.

        self.fs_context.m = self.area_exp
        self.fs_context.n = self.slope_exp

        # bypass fastscapelib_fortran global state
        h_bak = self.fs_context.h.copy()
        self.fs_context.h = self.elevation.flatten()

        if self.receivers.ndim == 1:
            fs.streampowerlawsingleflowdirection()
        else:
            fs.streampowerlaw()

        erosion_flat = self.elevation.ravel() - self.fs_context.h
        self.erosion = erosion_flat.reshape(self.shape)

        # restore fastscapelib_fortran global state
        self.fs_context.h = h_bak

    @chi.compute
    def _chi(self):
        chi_arr = np.empty_like(self.elevation, dtype='d')
        self.fs_context.copychi(chi_arr.ravel())

        return chi_arr


@xs.process
class DifferentialStreamPowerChannel(StreamPowerChannel):
    """Stream-Power channel (differential) erosion.

    Channel incision coefficient may vary depending on whether the
    topographic surface is bare rock or covered by a soil (sediment)
    layer.

    """
    k_coef_bedrock = xs.variable(
        dims=[(), ('y', 'x')],
        description='bedrock channel incision coefficient'
    )
    k_coef_soil = xs.variable(
        dims=[(), ('y', 'x')],
        description='soil (sediment) channel incision coefficient'
    )

    k_coef = xs.variable(
        dims=('y', 'x'),
        intent='out',
        description='differential channel incision coefficient'
    )

    soil_thickness = xs.foreign(UniformSoilLayer, 'thickness')

    def run_step(self):
        self.k_coef = np.where(self.soil_thickness <= 0.,
                               self.k_coef_bedrock,
                               self.k_coef_soil)

        super(DifferentialStreamPowerChannel, self).run_step()


@xs.process
class StreamPowerChannelTD(StreamPowerChannel):
    """Extended stream power channel erosion, transport and deposition."""

    # TODO: https://github.com/fastscape-lem/fastscapelib-fortran/pull/25
    # - update input var dimensions
    # - set self.get_context.g instead of g1 and g2

    g_coef = xs.variable(
        #dims=[(), ('y', 'x')],
        description='detached bedrock transport/deposition coefficient'
    )

    def _set_g_in_context(self):
        # TODO: set g instead
        self.fs_context.g1 = self.g_coef
        self.fs_context.g2 = -1.


@xs.process
class DifferentialStreamPowerChannelTD(DifferentialStreamPowerChannel):
    """Extended stream power channel (differential) erosion, transport and
    deposition.

    Both channel incision and transport/deposition coefficients may
    vary depending on whether the topographic surface is bare rock or
    covered by a soil (sediment) layer.

    """
    # TODO: https://github.com/fastscape-lem/fastscapelib-fortran/pull/25
    # - update input var dimensions
    # - set self.get_context.g instead of g1 and g2

    g_coef_bedrock = xs.variable(
        #dims=[(), ('y', 'x')],
        description='detached bedrock transport/deposition coefficient'
    )

    g_coef_soil = xs.variable(
        #dims=[(), ('y', 'x')],
        description='soil (sediment) transport/deposition coefficient'
    )

    g_coef = xs.variable(
        dims=('y', 'x'),
        intent='out',
        description='differential transport/deposition coefficient'
    )

    def _set_g_in_context(self):
        # TODO: set g instead
        self.fs_context.g1 = self.g_coef_bedrock
        self.fs_context.g2 = self.g_coef_soil

    def run_step(self):
        self.g_coef = np.where(self.soil_thickness <= 0.,
                               self.g_coef_bedrock,
                               self.g_coef_soil)

        super(DifferentialStreamPowerChannel, self).run_step()
