from datetime import date
import random
import os
import string
from itertools import compress
import re

import sys

from textx import metamodel_from_file


def create_mesh_preprocessor(create_cmd):
    # If no folder is specified for mesh creation, put it in default location
    if not create_cmd.folder:
        today = date.today().isoformat()

        # Generate a random ASCII string
        rnd = ''.join(random.choice(string.ascii_letters) for _ in range(10))

        # Generate candidate directory name
        path = os.path.join('meshes', '{}_{}'.format(today, rnd))

        create_cmd.folder = path

    if not create_cmd.name:
        create_cmd.name = 'block'


def set_mesh_units_preprocessor(set_cmd):
    # If no mesh units are specified, assume units are mm
    if not set_cmd.units:
        set_cmd.units = "mm"


def run_command_preprocessor(run_cmd):
    # Default to monodomain if simulation type isn't specified
    if not run_cmd.sim_type:
        run_cmd.sim_type = "monodomain"

    # Provide default location to save output
    if not run_cmd.output:
        today = date.today().isoformat()

        run_cmd.output = "{}_out".format(today)
        pass


class Simulation(object):

    def __init__(self):
        # Mesh specific commands
        self.mesh_name = ""
        self.mesh_size = [1, 1, 1]
        self.mesh_resolution = [100, 100, 100]
        self.mesh_size_factor = 0.1          # mesher expects this input to be in cm, whereas our default is mm
        self.mesh_resolution_factor = 1000   # mesher expects this input to be in um, whereas our default is mm
        self.mesh_centre = [0.0, 0.0, 0.0]

        # Stimulus commands
        self.n_stim = 0
        self.stim_duration = list()
        self.stim_strength = list()
        self.stim_location = list()
        self.stim_size = list()
        self.stim_loc_factor = 1000     # mesher expects this input to be in um, whereas our default is mm
        self.stim_size_factor = 1000    # mesher expects this input to be in um, whereas our default is mm

        # Parameter commands
        self.param_file = ''
        self.run_cmd = True

    def __str__(self):
        return "Mesh is saved at {}".format(self.mesh_name)

    def set_dry_run(self, cmd):
        if cmd == "DryRun":
            self.run_cmd = False

    def set_mesh(self, cmd):
        if cmd.setting.lower() == "size":
            self.mesh_size = [cmd.x, cmd.y, cmd.z]

        elif cmd.setting.lower() == "resolution":
            self.mesh_resolution = [cmd.x, cmd.y, cmd.z]

        elif cmd.setting.lower() == "units to be":
            # mesher expects mesh_size for baths, tissue, etc., to be in units of cm,
            # while it expects the mesh_resolution to be in units of um.
            if cmd.units == "mm":
                self.mesh_size_factor = 0.1
                self.mesh_resolution_factor = 1000
            elif cmd.units == "um":
                self.mesh_size_factor = 100
                self.mesh_resolution_factor = 1

        elif cmd.setting.lower() == "centre at":
            self.mesh_centre = [cmd.x, cmd.y, cmd.z]

        else:
            raise Exception('Unexpected value given for MeshSetCmd: {}'.format(cmd.setting))
        return None

    def create_mesh(self, cmd):
        if not os.path.isdir(cmd.folder):
            os.makedirs(cmd.folder)
        self.mesh_name = os.path.join(cmd.folder, cmd.name)
        if os.path.isfile(self.mesh_name+'.pts'):
            print("Mesh already exists.")
            return
        size = [i_size * self.mesh_size_factor for i_size in self.mesh_size]
        resolution = [i_res * self.mesh_resolution_factor for i_res in self.mesh_resolution]
        centre = [c * self.mesh_size_factor for c in self.mesh_centre]

        # Combine options
        mesh_opts = {"-size[0]": str(size[0]),
                     "-size[1]": str(size[1]),
                     "-size[2]": str(size[2]),
                     "-bath[0]": "-0.0",
                     "-bath[1]": "0.0",
                     "-bath[2]": "-0.0",
                     "-center[0]": str(centre[0]),
                     "-center[1]": str(centre[1]),
                     "-center[2]": str(centre[2]),
                     "-resolution[0]": str(resolution[0]),
                     "-resolution[1]": str(resolution[1]),
                     "-resolution[2]": str(resolution[2]),
                     "-mesh": str(self.mesh_name),
                     "-Elem3D": "0",
                     "-fibers.rotEndo": "0.0",
                     "-fibers.rotEpi": "0.0",
                     "-fibers.sheetEndo": "90.0",
                     "-fibers.sheetEpi": "90.0",
                     "-periodic": "0",
                     "-periodic_tag": "1234",
                     "-perturb": "0.0"}

        print("/usr/local/bin/mesher")
        for key in mesh_opts:
            print('  {} {}'.format(key, mesh_opts[key]))
        if self.run_cmd:
            mesh_str = ["/usr/local/bin/mesher"] + ['{} {}'.format(key, mesh_opts[key]) for key in mesh_opts]
            os.system(' '.join(mesh_str))

    def set_stimulus(self, cmd):
        self.n_stim = self.n_stim + 1
        self.stim_duration.append(cmd.duration)
        self.stim_strength.append(cmd.strength)

        if cmd.loc_units == "mm":
            self.stim_loc_factor = 1000
        elif cmd.loc_units == "um":
            self.stim_loc_factor = 1
        location = [cmd.loc_x, cmd.loc_y, cmd.loc_z]
        location = [loc * self.stim_loc_factor for loc in location]
        self.stim_location.append(location)

        if cmd.size_units == "mm":
            self.stim_size_factor = 1000
        elif cmd.size_units == "um":
            self.stim_size_factor = 1
        size = [cmd.size_x, cmd.size_y, cmd.size_z]
        size = [s * self.stim_size_factor for s in size]
        self.stim_size.append(size)

    def parse_input_param_file(self):
        """ Parse the .par input file

        Check the options provided via the input parameter file to flag for any settings that will conflict with user
        specified commands
        """

        with open(self.param_file, 'r') as pFile:
            lines = pFile.readlines()

        # Remove newline commands, and comment lines (start with #) and empty lines
        lines = [line.replace('\n', '') for line in lines]
        lines = [line for line in lines if not line.startswith('#')]
        lines = [line for line in lines if not line == '']

        # Split and extract the flags and their values, while removing whitespace
        lines = [line.split('=') for line in lines]
        lines = [[line_split.strip() for line_split in line] for line in lines]

        lines = [['-'+line[0], line[1]] for line in lines]
        lines_dict = dict()
        for line in lines:
            lines_dict[line[0]] = line[1]
        return lines_dict

    def run_command(self, cmd):
        # Check if data already exists in output location, and abort if so
        if os.path.isdir(cmd.output):
            continue_chk = input('Output location already exists - do you wish to continue and overwrite (y/n)!')
            if continue_chk.lower() == 'n':
                raise Exception('Simulation aborting!')
            elif continue_chk.lower() == 'y':
                pass
            else:
                raise Exception('Incorrect value given - rewrite to fail more gracefully...')

        if cmd.sim_type == "monodomain":
            bidomain_flag = "0"
        elif cmd.sim_type == "bidomain":
            bidomain_flag = "1"
        else:
            raise Exception('Improper value passed')

        # stim_string = ''
        stim_opts = dict()
        for i_stim, (dur, strength, loc, size) in enumerate(zip(self.stim_duration, self.stim_strength,
                                                                self.stim_location, self.stim_size)):
            stim_opts = {'-stimulus[{}].name'.format(i_stim): 'S1',
                         '-stimulus[{}].stimtype'.format(i_stim): 0,
                         '-stimulus[{}].strength'.format(i_stim): strength,
                         '-stimulus[{}].duration'.format(i_stim): dur,
                         '-stimulus[{}].x0'.format(i_stim): loc[0],
                         '-stimulus[{}].xd'.format(i_stim): size[0],
                         '-stimulus[{}].y0'.format(i_stim): loc[1],
                         '-stimulus[{}].yd'.format(i_stim): size[1],
                         '-stimulus[{}].z0'.format(i_stim): loc[2],
                         '-stimulus[{}].zd'.format(i_stim): size[2]}

        # TODO: Find out way to determine parab_options_file and ellip_options_file
        cmd_opts = {'-bidomain': bidomain_flag,
                    '-ellip_use_pt': '0',
                    '-parab_use_pt': '0',
                    '-parab_options_file':
                        '/usr/local/lib/python3.8/dist-packages/carputils/resources/petsc_options/ilu_cg_opts',
                    '-ellip_options_file':
                        '/usr/local/lib/python3.8/dist-packages/carputils/resources/petsc_options/gamg_cg_opts',
                    '-simID': cmd.output,
                    '-meshname': self.mesh_name,
                    '-dt': '25',
                    '-tend': str(cmd.duration),
                    '-num_phys_regions': '2',
                    '-phys_region[0].name': '"Intracellular domain"',
                    '-phys_region[0].ptype': '0',
                    '-phys_region[0].num_IDs': '1',
                    '-phys_region[0].ID[0]': '1',
                    '-phys_region[1].name': '"Extracellular domain"',
                    '-phys_region[1].ptype': '1',
                    '-phys_region[1].num_IDs': '1',
                    '-phys_region[1].ID[0]': '1',
                    '-num_stim': str(self.n_stim)}

        cmd_keys = list()
        for key in cmd_opts:
            cmd_keys.append(key)

        # Want to position param_file as the first option to openCARP, and thus one to be over-ridden against
        # following commands
        if self.param_file:
            # TODO: Rewrite this to be OS agnostic re: potential file separators
            if self.param_file.startswith('/'):
                cmd_opts['+F'] = self.param_file
            else:
                cmd_opts['+F'] = './' + self.param_file
            cmd_keys.insert(cmd_keys.index('-bidomain')+1, '+F')
            param_opts = self.parse_input_param_file()

            repeated_keys = [True if key in cmd_keys else False for key in param_opts]

            repeated_keys = list(compress(param_opts.keys(), repeated_keys))
            warning_list = list()
            for key in repeated_keys:
                if key == '-num_stim':
                    warning_list.append('Parameter file defines stimulus currents as:')
                    for i_stim in range(int(param_opts['-num_stim'])):
                        warning_list.append('\tCurrent {}:'.format(i_stim))
                        stim_match = re.compile('-stim.*[{}]'.format(0))
                        matched_keys = list(filter(stim_match.match, param_opts.keys()))
                        for match_key in matched_keys:
                            warning_list.append('\t\t{} = {}'.format(match_key, param_opts[match_key]))
                    warning_list.append('User commands redefine stimulus as:')
                    for i_stim in range(int(cmd_opts['-num_stim'])):
                        warning_list.append('\tCurrent {}:'.format(i_stim))
                        stim_match = re.compile('-stim.*[{}]'.format(0))
                        matched_keys = list(filter(stim_match.match, stim_opts.keys()))
                        for match_key in matched_keys:
                            warning_list.append('\t\t{} = {}'.format(match_key, stim_opts[match_key]))
                if cmd_opts[key] != param_opts[key]:
                    warning_list.append('Parameter file defines {} as {}, input defines it as {}'.
                                        format(key, param_opts[key], cmd_opts[key]))
            if warning_list:
                for warning in warning_list:
                    print(warning)
                continue_val = input('Do you wish to continue? (y/n)')
                if continue_val.lower() == 'n':
                    raise Exception('Simulation aborted at user request.')

        print('/usr/local/bin/openCARP')
        for key in cmd_opts:
            print('  {} {}'.format(key, cmd_opts[key]))
        for key in stim_opts:
            print('  {} {}'.format(key, stim_opts[key]))
        if self.run_cmd:
            opts_str = ['/usr/local/bin/openCARP'] + ['{} {}'.format(key, cmd_opts[key]) for key in cmd_keys] + \
                       ['{} ' '{}'.format(key, stim_opts[key]) for key in stim_opts]
            os.system(' '.join(opts_str))

    def interpret(self, model):
        for cmd in model.commands:
            cmd_name = cmd.__class__.__name__
            if cmd_name == "DryRun":
                self.set_dry_run(cmd_name)
            elif cmd_name == "SetMesh":
                self.set_mesh(cmd)
            elif cmd_name == "CreateMesh":
                self.create_mesh(cmd)
            elif cmd_name == "StimulusCommand":
                self.set_stimulus(cmd)
            elif cmd_name == "ParameterCommand":
                self.param_file = cmd.param_file
            elif cmd_name == "RunCommand":
                self.run_command(cmd)
            else:
                raise Exception('Unexpected command received')


def main():
    assert len(sys.argv) == 2, "Need to pass .carp file to process!"

    this_folder = os.path.dirname(__file__)

    carp_mm = metamodel_from_file(os.path.join(this_folder, 'carp_dsl.tx'), debug=False)

    # Register object processor for CreateMesh
    obj_processors = {'CreateMesh': create_mesh_preprocessor,
                      'SetMesh': set_mesh_units_preprocessor,
                      'RunCommand': run_command_preprocessor}
    carp_mm.register_obj_processors(obj_processors)

    print("Parsing {}".format(os.path.join(this_folder, sys.argv[1])))
    example_simulation = carp_mm.model_from_file(os.path.join(this_folder, sys.argv[1]))
    # example_simulation = carp_mm.model_from_file(os.path.join(this_folder, '01_basic_usage.carp'))

    simulation = Simulation()
    simulation.interpret(example_simulation)


if __name__ == "__main__":
    main()
