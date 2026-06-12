import argparse
import json
import sys
import math
import pygrib

def get_key(msg, key, default=0):
    """
    Safely extracts an attribute/key from a pygrib message.
    Catches RuntimeError because pygrib throws C-level key errors 
    instead of standard Python AttributeErrors.
    """
    try:
        return getattr(msg, key)
    except (RuntimeError, AttributeError):
        return default

def is_selected(msg, args):
    """
    Replicates the filtering logic in GribRecordWriter.isSelected()
    """
    # Filter by Category (--fc)
    if args.fc is not None and get_key(msg, 'parameterCategory') != args.fc:
        return False
        
    # Filter by Parameter (--fp)
    if args.fp is not None:
        param_num = get_key(msg, 'parameterNumber')
        if args.fp.lower() == "wind":
            # 2 = U-component, 3 = V-component
            if param_num not in (2, 3):
                return False
        else:
            try:
                if param_num != int(args.fp):
                    return False
            except ValueError:
                return False

    # Filter by Surface Type (--fs)
    if args.fs is not None and get_key(msg, 'typeOfFirstFixedSurface') != args.fs:
        return False

    # Filter by Surface Value (--fv)
    if args.fv is not None and get_key(msg, 'level') != args.fv:
        return False

    return True

def extract_header(msg, print_names):
    """
    Extracts the header information from a PyGrib message, mapping 
    to the structure expected by the original cambecc/grib2json tool.
    """
    header = {
        "discipline": get_key(msg, 'discipline', 0),
        "gribEdition": get_key(msg, 'edition', 2),
        "gribLength": get_key(msg, 'totalLength', 0),  # Corrected key for GRIB message size
        "center": get_key(msg, 'center', 0),
        "refTime": str(get_key(msg, 'validDate', '')),
        "parameterCategory": get_key(msg, 'parameterCategory', 0),
        "parameterNumber": get_key(msg, 'parameterNumber', 0),
        "surface1Type": get_key(msg, 'typeOfFirstFixedSurface', 0),
        "surface1Value": get_key(msg, 'level', 0.0),
        "forecastTime": get_key(msg, 'forecastTime', 0),
        
        # Grid shape & Definitions
        "nx": get_key(msg, 'Ni', 0),
        "ny": get_key(msg, 'Nj', 0),
        "lo1": get_key(msg, 'longitudeOfFirstGridPointInDegrees', 0.0),
        "la1": get_key(msg, 'latitudeOfFirstGridPointInDegrees', 0.0),
        "lo2": get_key(msg, 'longitudeOfLastGridPointInDegrees', 0.0),
        "la2": get_key(msg, 'latitudeOfLastGridPointInDegrees', 0.0),
        "dx": get_key(msg, 'jDirectionIncrementInDegrees', get_key(msg, 'DxInMetres', 0.0)),
        "dy": get_key(msg, 'iDirectionIncrementInDegrees', get_key(msg, 'DyInMetres', 0.0))
    }

    if print_names:
        header["centerName"] = get_key(msg, 'cfName', get_key(msg, 'name', 'unknown'))
        header["parameterNumberName"] = get_key(msg, 'shortName', 'unknown')
        header["parameterUnit"] = get_key(msg, 'units', 'unknown')

    return header

def replace_nan(value):
    """Replicates the FloatValue.java behavior for handling NaNs/Infinities"""
    if math.isnan(value):
        return "NaN"
    elif math.isinf(value):
        return "Infinity" if value > 0 else "-Infinity"
    return round(value, 4)

def main():
    parser = argparse.ArgumentParser(description="GRIB to JSON converter (Python port)")
    parser.add_argument("FILE", help="GRIB2 file to process")
    parser.add_argument("-c", "--compact", action="store_true", help="enable compact Json formatting")
    parser.add_argument("-d", "--data", action="store_true", help="print GRIB record data")
    parser.add_argument("--fc", type=int, help="select records with this numeric category")
    parser.add_argument("--fp", type=str, help="select records with this numeric parameter")
    parser.add_argument("--fs", type=int, help="select records with this numeric surface type")
    parser.add_argument("--fv", type=float, help="select records with this numeric surface value")
    parser.add_argument("-n", "--names", action="store_true", help="print names of numeric codes")
    parser.add_argument("-o", "--output", type=str, help="write output to the specified file (default is stdout)")
    
    args = parser.parse_args()

    records = []

    try:
        grbs = pygrib.open(args.FILE)
        
        for msg in grbs:
            if is_selected(msg, args):
                record = {
                    "header": extract_header(msg, args.names)
                }
                
                if args.data:
                    data_values = msg.values.flatten().tolist()
                    record["data"] = [replace_nan(val) for val in data_values]
                
                records.append(record)
                
        grbs.close()
        
    except IOError as e:
        print(f"Error opening file {args.FILE}: {e}")
        sys.exit(1)

    # Format JSON Output
    indent = None if args.compact else 4
    json_output = json.dumps(records, indent=indent)

    if args.output:
        with open(args.output, 'w') as f:
            f.write(json_output)
    else:
        print(json_output)

if __name__ == "__main__":
    main()