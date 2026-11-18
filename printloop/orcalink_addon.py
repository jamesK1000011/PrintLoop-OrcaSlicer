# SPDX-License-Identifier: AGPL-3.0-only
# What OrcaSlicer Agent Link (orcalink) loads from this package: the
# PrintLoop tools. orcalink finds this module by convention (a package on
# the path, or in a folder that ORCALINK_ADDONS lists, that holds an
# orcalink_addon module) and never names PrintLoop. Without PrintLoop
# installed, orcalink adds no tool and spends no tokens.
from . import CREDIT, LICENSE, VERSION  # noqa: F401


def tools(ctx):
    from . import tools as T

    return T.specs(ctx)
