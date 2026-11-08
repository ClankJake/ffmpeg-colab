# pylint: disable = C0114
from options import Options
from build_utils import run_fg


def pre_configure(options: Options):
    """
    Pre configuration build patch
    """
    # O FFmpeg >= 8 exporta `dec_init` em fftools/ffmpeg_dec.c e o libbluray também define
    # `dec_init` (src/libbluray/decoders/dec.c): no link estático dá "multiple definition".
    # Renomeia o símbolo do libbluray (definição e usos) antes de compilar.
    run_fg(
        "bash",
        "-c",
        r"grep -rlw dec_init src | xargs -r sed -i 's/\bdec_init\b/bd_dec_init/g'",
        silent=options.silent,
    )
    run_fg("autoreconf", "-fiv")
