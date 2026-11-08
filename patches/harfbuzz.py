# pylint: disable = C0114
"""HarfBuzz via Meson (o port CMake do HarfBuzz estรก deprecado e deve sair)."""
import re
from options import Options


def pre_dependency(ctx, options: Options):
    """
    Pre dependency build patch
    """
    if "libfreetype" in options.targets:
        ctx.add_configuration_params("-Dfreetype=enabled")
        ctx.add_dependencies("libfreetype")
        return
    ctx.add_configuration_params("-Dfreetype=disabled")


def pre_configure(ctx, options: Options):
    """
    Pre configuration build patch
    """
    version = re.findall(r"harfbuzz-(.+)\.tar", ctx.download_params[1])[0]
    ctx.add_configuration_params(
        f"--libdir={options.release_dir}/lib",
        f"{options.target_dir}/harfbuzz-{version}",
    )
