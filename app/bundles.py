from flask import request
from app.configuration import SAMPLE_PATH
from app.diagnostics import RampError
from app.intake.schemas import COLUMNS, OPTIONAL_CHANNELS, REQUIRED_CHANNELS


def sample_set(name):
    if name not in ('clean','dirty'):
        raise RampError('SAMPLE',404)
    bundle = {}
    for key in COLUMNS:
        path = SAMPLE_PATH/f'{name}-{key}.csv'
        if key in OPTIONAL_CHANNELS and not path.exists():
            continue
        bundle[key] = path.read_bytes()
    return bundle


def submitted():
    if request.method=='GET':
        return sample_set(request.args.get('sample','dirty'))
    body = request.get_json(silent=True)
    if isinstance(body,dict) and set(body)=={'sample'} and isinstance(body['sample'],str):
        return sample_set(body['sample'])
    required = set(REQUIRED_CHANNELS)
    allowed = set(COLUMNS)
    if not (isinstance(body,dict) and required <= body.keys() <= allowed
            and all(isinstance(v,str) for v in body.values())):
        raise RampError('BUNDLE')
    try:
        return {key:value.encode() for key,value in body.items()}
    except UnicodeEncodeError as exc:
        raise RampError('FILE') from exc
