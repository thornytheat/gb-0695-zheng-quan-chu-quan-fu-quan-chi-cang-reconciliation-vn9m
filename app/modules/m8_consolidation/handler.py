from flask import Blueprint, request, jsonify
from app.pipeline import calculate
from app.numeric import serial
bp=Blueprint('m8',__name__)
@bp.route('/api/m8', methods=['GET','POST'])
def module_8():
    payload=request.get_json(silent=True) or {}
    result=calculate(payload.get('csv'), stop=8)
    return jsonify(serial(result['stages']['8']))
