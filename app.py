from flask import Flask, request, render_template, send_from_directory, redirect, url_for
import os
import yaml
import json

app = Flask(__name__)

# Ruta absoluta para la carpeta uploads
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return 'No file part', 400
    file = request.files['file']
    if file.filename == '':
        return 'No selected file', 400
    if file:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(filepath)
        
        # Convertir el archivo a YAML
        yaml_filename = convert_to_yaml(filepath)

        return render_template('download.html', filename=yaml_filename)


import os
import yaml

def convert_to_yaml(filename):
    data = {           
        "title": "",
        "jobid": "",
        "files": {},
        "crtout": {},
        "gases": [],
        "control_volumes": [],
        "control_functions": [],
        "flow_paths": [],
        "sinks": [],
        "outputs": [],
        "external_data_files": [],
        "melcor_configuration": {}
    }

    current_volume = None
    current_flow_path = None  # Inicializar variable para flow path actual

    with open(filename, 'r') as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith('*'):
                continue

            tokens = line.split()
            if len(tokens) == 0:
                continue

            # Identificar secciones
            if tokens[0].lower() == "title" and len(tokens) > 1:
                data["title"] = " ".join(tokens[1:])
            elif tokens[0].lower() == "jobid" and len(tokens) > 1:
                data["jobid"] = tokens[1]
            elif tokens[0].lower() == "restartf" and len(tokens) > 1:
                data["files"]["restartf"] = tokens[1]
            elif tokens[0].lower() == "outputf" and len(tokens) > 1:
                data["files"]["outputf"] = tokens[1]
            elif tokens[0].lower() == "diagf" and len(tokens) > 1:
                data["files"]["diagf"] = tokens[1]
            elif tokens[0].lower() == "stopf" and len(tokens) > 1:
                data["files"]["stopf"] = tokens[1]
            elif tokens[0].lower() == "tstart" and len(tokens) > 1:
                try:
                    data["crtout"]["tstart"] = float(tokens[1])
                except ValueError:
                    continue
            elif tokens[0].lower() == "dttime" and len(tokens) > 1:
                try:
                    data["crtout"]["dttime"] = float(tokens[1])
                except ValueError:
                    continue

            # Procesar gases
            elif tokens[0].startswith("NCG") and len(tokens) >= 3:
                try:
                    gas_id = int(tokens[2])
                    gas_name = tokens[1]
                    data["gases"].append({
                        "id": gas_id,
                        "name": gas_name
                    })
                except ValueError:
                    continue
            #Funciona <-
            # Parser de los volúmenes de control (CV)
            elif tokens[0].startswith("CV") and len(tokens) >= 3:
                if tokens[0].endswith("00"):  # Inicio de un nuevo control volume
                    current_volume = {
                        "id": tokens[0],
                        "name": tokens[1],
                        "type": tokens[2],
                        "properties": {},
                        "altitude_volume": []
                    }
                    data["control_volumes"].append(current_volume)

                elif tokens[0][-2] == "A" and tokens[0][-1].isdigit():
                    key_value_pairs = {}
                    # Procesar pares clave-valor de los volúmenes de control
                    for i in range(1, len(tokens), 2):
                        if i + 1 < len(tokens):
                            key = tokens[i]
                            try:
                                value = float(tokens[i + 1])
                            except ValueError:
                                value = tokens[i + 1]
                            key_value_pairs[key] = value

                    if current_volume is not None:
                        current_volume["properties"].update(key_value_pairs)

                elif tokens[0].endswith("B2") and len(tokens) >= 3:
                    try:
                        altitude = float(tokens[1])
                        volume = float(tokens[2])
                        if current_volume is not None:
                            current_volume["altitude_volume"].append({
                                "altitude": altitude,
                                "volume": volume
                        })
                    except ValueError:
                        continue

            elif tokens[0].startswith("FL") and len(tokens) >= 3:
                if tokens[0].endswith("00"):  # Inicio de un nuevo flow path
                    current_flow_path = {
                        "id": tokens[0],  # Identificador del flow path
                        "name":tokens[1],
                        "from_control_volume": {
                            "id": tokens[2],  # Volumen de control de origen
                            "height": float(tokens[4])  # Altura del volumen de control de origen
                        },
                        "to_control_volume": {
                            "id": tokens[3],  # Volumen de control de destino
                            "height": float(tokens[5])  # Altura del volumen de control de destino
                        },
                        "geometry": {},  # Inicializa el diccionario para la geometría
                        "segment_parameters": {}, 
                        "junction_limits": {},
                        "time_dependent_flow_path": {} 
                    }
                    data["flow_paths"].append(current_flow_path)

                elif tokens[0].endswith("01") and len(tokens) >= 4:#"from_control_volume" in current_flow_path and "to_control_volume" in current_flow_path:
                    # Campo '01': Flow path geometry
                    if "geometry" in current_flow_path:
                        current_flow_path["geometry"] = {
                            "area": float(tokens[1]),  # Área del flow path
                            "length": float(tokens[2]),  # Longitud del flow path
                            "fraction_open": float(tokens[3]) if len(tokens) > 3 else None,  # Fracción del flow path abierto
                        }

                elif tokens[0].endswith("S0") and len(tokens) >= 4:  # Campo S0
                    # Campo S0: Piping segment parameters
                    if "segment_parameters" in current_flow_path:
                        current_flow_path["segment_parameters"] = {
                            "area": float(tokens[1]),  # Área del segmento de flujo
                            "length": float(tokens[2]),  # Longitud del segmento
                            "hydraulic_diameter": float(tokens[3])  # Diámetro hidráulico del segmento
                        }

                elif tokens[0].endswith("0F") and len(tokens) >= 3:
                    # Campo '0F': Junction limits, from volume
                    if "junction_limits" in current_flow_path:
                        current_flow_path["junction_limits"]["from_volume"] = {
                            "bottom_opening_elevation": float(tokens[1]),  # Elevación del fondo de la apertura de la junta para el volumen de origen
                            "top_opening_elevation": float(tokens[2])  # Elevación de la parte superior de la apertura de la junta para el volumen de origen
                        }

                elif tokens[0].endswith("0T") and len(tokens) >= 3:
                    # Campo '0T': Junction limits, to volume
                    if "junction_limits" in current_flow_path:
                        current_flow_path["junction_limits"]["to_volume"] = {
                            "bottom_opening_elevation": float(tokens[1]),  # Elevación del fondo de la apertura de la junta para el volumen de destino
                            "top_opening_elevation": float(tokens[2])  # Elevación de la parte superior de la apertura de la junta para el volumen de destino
                        }

                elif tokens[0].endswith("T0") and len(tokens) >= 3:
                    # Campo 'T0': Time dependent flow path
                        current_flow_path["time_dependent_flow_path"] = {
                            "type_flag": int(tokens[1]),  # Tipo de flujo dependiente del tiempo
                            "function_number": int(tokens[2])  # Número de función tabular o de control
                        }


                        
            #Funciona ->
            elif tokens[0].startswith("CF") and len(tokens) >= 4:
                if tokens[0].endswith("00"):
                    current_cf = {
                        "name": tokens[1],  # Nombre definido por el usuario de la función de control
                        "type": tokens[2],  # Tipo de función de control
                        "num_arguments": int(tokens[3]),  # Número de argumentos
                        "scale_factor": float(tokens[4]),  # Factor de escala multiplicativo
                        "additive_constant": float(tokens[5]) if len(tokens) > 5 else 0.0  # Constante aditiva (opcional)
                    }
                    data["control_functions"].append(current_cf)

                elif len(tokens) >= 4 and tokens[0][2:].isdigit() and int(tokens[0][2:]) >= 10:  # Control Function Arguments (kk >= 10)
                    if current_cf is not None:
                        argument = {
                            "scale_factor": float(tokens[1]),  # Factor de escala multiplicativo
                            "additive_constant": float(tokens[2]),  # Constante aditiva
                            "database_element": tokens[3]  # Identificador del elemento de la base de datos
                        }
                        if "arguments" not in current_cf:
                            current_cf["arguments"] = []
                            current_cf["arguments"].append(argument)
            # <-Funciona
            # Procesar archivos externos
            elif tokens[0].startswith("EDF") and len(tokens) >= 2:
                if tokens[0].endswith("00"):  # External Data File Definition Record
                    current_edf = {
                        "name": tokens[1],  # User defined external data file name
                        "channels": int(tokens[2]),  # Number of channels (dependent variables)
                        "mode": tokens[3],  # Direction and mode of information transfer
                        "file_specification": {}  # Initialize file specification as empty
                    }
                    data["external_data_files"].append(current_edf)

                elif tokens[0].endswith("01"):  # File Specification
                    # Campo '01':File Specification
                    if "file_specification" in current_edf:
                        current_edf["file_specification"] = {
                            "file_name": tokens[1]  # Name of the file in the operating system
                        }

                elif tokens[0].endswith("02") and len(tokens) >= 2:
                    # Campo '02': External Data File Format
                    current_edf["file_format"] = tokens[1]  # Elimina comillas simples si están presentes

                
                elif tokens[0].endswith("10") and len(tokens) >= 3:
                    print(f"Tokens: {tokens}")
                    # Campo '10': Write Increment Control for WRITE or PUSH File
                    current_edf["write_increment_control"] = {
                        "time_effective": float(tokens[1]),  # Tiempo en el que el incremento de salida entra en efecto
                        "time_increment": float(tokens[2])  # Incremento de tiempo entre los registros de salida
                    }

                elif tokens[0][-2] == "A" and tokens[0][-1].isdigit():
                    # Inicializa el diccionario si no existe
                    if "channel_variables" not in current_edf:
                        current_edf["channel_variables"] = {}

                    # Usa el índice como clave y el valor como el token correspondiente
                    index = tokens[0][-1]  # Obtén el índice del campo
                    value = tokens[1].strip()  # Obtén el valor del token, eliminando espacios

                    # Almacena el valor en el diccionario de variables del canal
                    current_edf["channel_variables"][f"A{index}"] = value
            #Funciona->

            # Procesar configuración de MELCOR
            elif tokens[0].lower() == "restartfile" and len(tokens) > 1:
                data["melcor_configuration"]["restartfile"] = tokens[1]
            elif tokens[0].lower() == "outputfile" and len(tokens) > 1:
                data["melcor_configuration"]["outputfile"] = tokens[1]
            elif tokens[0].lower() == "diagfile" and len(tokens) > 1:
                data["melcor_configuration"]["diagfile"] = tokens[1]
            elif tokens[0].lower() == "cpu_settings" and len(tokens) >= 3:
                try:
                    data["melcor_configuration"]["cpu_settings"] = {
                        "cpuleft": float(tokens[1]),
                        "cpulim": float(tokens[2])
                    }
                except ValueError:
                    continue
            elif tokens[0].lower() == "time_settings" and len(tokens) >= 4:
                try:
                    data["melcor_configuration"]["time_settings"] = {
                        "tend": float(tokens[1]),
                        "softdtmin": float(tokens[2]),
                        "time1": list(map(float, tokens[3:]))
                    }
                except ValueError:
                    continue

    yaml_filename = os.path.basename(filename).replace('.inp', '.yaml')
    yaml_path = os.path.join(app.config['UPLOAD_FOLDER'], yaml_filename)  
    with open(yaml_path, 'w') as yaml_file:
        yaml.dump(data, yaml_file, default_flow_style=False)

    return yaml_filename


 

@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.isfile(filepath):
        return f"Archivo {filename} no encontrado", 404
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

# Nueva ruta para editar un archivo YAML
@app.route('/edit/<filename>', methods=['GET', 'POST'])
def edit_file(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    if request.method == 'POST':
        # Guardar los cambios en el YAML
        content = request.form['yaml_content']
        with open(file_path, 'w') as f:
            yaml.dump(yaml.safe_load(content), f)
        
        # Redirigir a la página inicial después de guardar
        return redirect(url_for('index'))
    
    # Cargar el contenido del YAML para editar
    with open(file_path, 'r') as f:
        yaml_content = f.read()
    
    return render_template('editor.html', yaml_content=yaml_content)
@app.route('/visualize/<filename>', methods=['GET'])
def visualize_file(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    with open(file_path, 'r') as file:
        yaml_data = yaml.safe_load(file)
    
    # Crear nodos para control volumes (habitaciones)
    nodes = [{'id': cv['id'], 'label': cv['name'], 'group': 'control_volume'} for cv in yaml_data['control_volumes']]
    
    # Crear nodos para gases
    nodes += [{'id': gas['id'], 'label': gas['name'], 'group': 'gas'} for gas in yaml_data['gases']]
    
    # Crear nodos para flujos (componentes)
    nodes += [{'id': flow['id'], 'label': flow['name'], 'group': 'flow'} for flow in yaml_data['flows']]
    
    # Crear aristas entre control volumes y gases
    edges = []
    for cv in yaml_data['control_volumes']:
        for gas in yaml_data['gases']:
            edges.append({'from': cv['id'], 'to': gas['id'], 'label': 'contains'})
    
    # Crear aristas entre control volumes y flujos
    for cv in yaml_data['control_volumes']:
        for flow in yaml_data['flows']:
            edges.append({'from': cv['id'], 'to': flow['id'], 'label': 'flow'})
    
    graph_data = {
        'nodes': nodes,
        'edges': edges
    }
    
    return render_template('visualize.html', graph_data=json.dumps(graph_data))

if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    app.run(debug=True)
