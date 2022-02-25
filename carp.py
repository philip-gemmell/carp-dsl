from datetime import date
import random
import os
import string
from itertools import compress
import re
import pandas as pd

import sys

from textx import metamodel_from_file


class CarpException(Exception):
    """Custom exception class to distinguish the faults we expect, compared to ones that are unintended..."""

    def __init__(self, msg, *args):
        super().__init__(args)
        self.msg = msg

    def __str__(self):
        return self.msg


class MeshException(CarpException):
    def __init__(self, msg, *args):
        super(MeshException, self).__init__(msg, args)

    def __str__(self):
        super(MeshException, self).__str__()


class Region(object):
    def __init__(self):
        self.name = None
        self.tag = None
        self.location = None
        self.size = None
        self.loc_factor = 1000     # mesher expects this input to be in um, whereas our default is mm
        self.size_factor = 1000    # mesher expects this input to be in um, whereas our default is mm


class Stimulus(object):
    def __init__(self):
        self.n_stim = 0
        self.start = 0.0
        self.bcl = None
        self.n_pulse = None
        self.duration = 0.0
        self.strength = 0.0
        self.location = None
        self.size = None
        self.loc_factor = 1000     # mesher expects this input to be in um, whereas our default is mm
        self.size_factor = 1000    # mesher expects this input to be in um, whereas our default is mm


class Simulation(object):

    def __init__(self):
        # Mesh specific commands
        self.mesh_name = ""
        self.mesh_size = [1, 1, 1]
        self.mesh_resolution = [100, 100, 100]
        self.mesh_size_factor = 0.1          # mesher expects this input to be in cm, whereas our default is mm
        self.mesh_resolution_factor = 1000   # mesher expects this input to be in um, whereas our default is mm
        self.mesh_centre = [0.0, 0.0, 0.0]
        self.mesh_tags = None

        # Region commands
        self.n_regions = 0
        self.regions = list()

        # Stimulus commands
        self.n_stim = 0
        self.stimulus = list()

        # Parameter commands
        self.param_file = ''
        self.run_cmd = True

    def __str__(self):
        return "Mesh is saved at {}".format(self.mesh_name)

    def set_mesh(self, cmd):
        if cmd.setting.lower() == "size":
            self.mesh_size = [cmd.x, cmd.y, cmd.z]
            # mesher expects mesh_size for baths, tissue, etc., to be in units of cm
            if cmd.meshUnits == "cm":
                self.mesh_size_factor = 1
            elif cmd.meshUnits == "mm":
                self.mesh_size_factor = 0.1
            elif cmd.meshUnit == "um":
                self.mesh_size_factor = 100
            else:
                raise MeshException('Unrecognised mesh size given')

        elif cmd.setting.lower() == "resolution":
            self.mesh_resolution = [cmd.x, cmd.y, cmd.z]
            # mesher expects mesh_resolution to be in units of um.
            if cmd.meshUnits == "cm":
                self.mesh_resolution_factor = 10000
            elif cmd.meshUnits == "mm":
                self.mesh_resolution_factor = 1000
            elif cmd.meshUnits == "um":
                self.mesh_resolution_factor = 1
            else:
                raise MeshException('Unrecognised resolution size given')

        elif cmd.setting.lower() == "centre at":
            self.mesh_centre = [cmd.x, cmd.y, cmd.z]

        else:
            raise MeshException('Unexpected value given for MeshSetCmd: {}'.format(cmd.setting))
        return None

    def create_mesh(self, cmd):
        if not os.path.isdir(cmd.folder):
            os.makedirs(cmd.folder)
        self.mesh_name = os.path.join(cmd.folder, cmd.name)
        if os.path.isfile(self.mesh_name+'.pts'):
            try:
                _check_user_input("Mesh already exists - do you wish to use existing mesh? (Y/n)")
            except CarpException as ex:
                _check_user_input("Do you wish to use overwrite existing mesh? (Y/n)")
            else:
                # Need to check the existing mesh actually works!
                self.use_mesh()
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

        self.mesh_tags = get_mesh_tag_list(self.mesh_name)

    def use_mesh(self):
        """ Function to check that mesh actually exists, and perform some basic checks on it """

        file_exists = [os.path.exists(self.mesh_name+file_ext) for file_ext in ['.pts', '.elem', '.lon']]
        if not all(file_exists):
            raise MeshException("Mesh doesn't exist!")

        self.mesh_tags = get_mesh_tag_list(self.mesh_name)
        return None

    def set_stimulus(self, cmd):
        self.n_stim = self.n_stim + 1
        stim_data = self.parse_stimulus_command(cmd)

        self.stimulus.append(stim_data)

    def parse_region_command(self, cmd):
        """ Process the data from a DefineRegion command to a Region class """

        new_region = Region()
        new_region.name = cmd.name

        if cmd.loc_cmd:
            new_region.location, new_region.loc_factor, new_region.size, new_region.size_factor = \
                parse_location_command(cmd.loc_cmd)
        elif cmd.tag_cmd:
            # Confirm tag exists in mesh
            # TODO: Rewrite this be accommodating of varying elements - currently only handles meshes of identical elem
            assert cmd.tag_cmd.tag in self.mesh_tags

            new_region.tag = cmd.tag_cmd.tag
        else:
            raise CarpException("Unexpected command in RegionCommand")

        return new_region

    def parse_stimulus_command(self, cmd):
        """ Process the data from a StimulusCommand to a Stimulus class """

        stim_data = Stimulus()

        stim_data.stim_start = cmd.start
        stim_data.duration = cmd.duration
        stim_data.strength = cmd.strength

        if cmd.bcl == 0:
            stim_data.bcl = None
        else:
            stim_data.bcl = cmd.bcl

        if cmd.n_pulse == 0:
            stim_data.n_pulse = None
        else:
            stim_data.n_pulse = cmd.n_pulse

        if cmd.loc_cmd:
            stim_data.location, stim_data.loc_factor, stim_data.size, stim_data.size_factor = \
                parse_location_command(cmd.loc_cmd)
        elif cmd.region:
            # Check region has been defined!
            region_names = [region.name for region in self.regions]
            assert cmd.region in region_names, "Region {} is not defined!".format(cmd.region)

            i_region = region_names.index(cmd.region)
            stim_data.location = self.regions[i_region].location
            stim_data.loc_factor = self.regions[i_region].loc_factor
            stim_data.size = self.regions[i_region].size
            stim_data.size_factor = self.regions[i_region].size_factor
        else:
            raise CarpException("Unexpected command input given in defining stimulus")

        return stim_data

    def define_region(self, cmd):
        self.n_regions += 1
        new_region = self.parse_region_command(cmd)

        self.regions.append(new_region)
        return None

    def run_command(self, cmd):
        """ Process all commands into openCARP suitable format """

        # Check if data already exists in output location, and abort if so
        if os.path.isdir(cmd.output):
            _check_user_input('Output location already exists - do you wish to continue and overwrite (Y/n)!')

        # Confirm all tags in the mesh are coded for
        set_tags = [region.tag for region in self.regions]
        tag_used = [True if tag in set_tags else False for tag in self.mesh_tags]
        if not all(tag_used):
            tags_unused = [i_tag for i_tag, tag in enumerate(tag_used) if tag is False]
            raise MeshException("Not all tags present in mesh used! Unused tags = {}".format(tags_unused))

        if cmd.sim_type == "monodomain":
            bidomain_flag = "0"
        elif cmd.sim_type == "bidomain":
            bidomain_flag = "1"
        else:
            raise CarpException('Improper value passed')

        stim_opts = prepare_stimulus_opts(self.stimulus)

        cmd_opts = dict()
        if self.param_file:
            # TODO: Rewrite this to be OS agnostic re: potential file separators
            if self.param_file.startswith('/'):
                cmd_opts['+F'] = self.param_file
            else:
                cmd_opts['+F'] = './' + self.param_file

        # TODO: Find out way to determine parab_options_file and ellip_options_file
        cmd_opts['-bidomain'] = bidomain_flag
        cmd_opts['-ellip_use_pt'] = '0'
        cmd_opts['-parab_use_pt'] = '0'
        cmd_opts['-parab_options_file'] = \
            '/usr/local/lib/python3.8/dist-packages/carputils/resources/petsc_options/ilu_cg_opts'
        cmd_opts['-ellip_options_file'] = \
            '/usr/local/lib/python3.8/dist-packages/carputils/resources/petsc_options/gamg_cg_opts'
        cmd_opts['-simID'] = cmd.output
        cmd_opts['-meshname'] = self.mesh_name
        cmd_opts['-dt'] = '25'
        cmd_opts['-tend'] = str(cmd.duration)
        cmd_opts['-num_phys_regions'] = '2'
        cmd_opts['-phys_region[0].name'] = '"Intracellular domain"'
        cmd_opts['-phys_region[0].ptype'] = '0'
        cmd_opts['-phys_region[0].num_IDs'] = '1'
        cmd_opts['-phys_region[0].ID[0]'] = '1'
        cmd_opts['-phys_region[1].name'] = '"Extracellular domain"'
        cmd_opts['-phys_region[1].ptype'] = '1'
        cmd_opts['-phys_region[1].num_IDs'] = '1'
        cmd_opts['-phys_region[1].ID[0]'] = '1'
        cmd_opts['-num_stim'] = str(self.n_stim)

        # Want to position param_file as the first option to openCARP, and thus one to be over-ridden against
        # following commands
        if self.param_file:
            check_param_conflicts(self.param_file, cmd_opts, stim_opts)

        # Print run command regardless of whether it is actually executed
        print('/usr/local/bin/openCARP')
        for key in cmd_opts:
            print('  {} {}'.format(key, cmd_opts[key]))
        for key in stim_opts:
            print('  {} {}'.format(key, stim_opts[key]))

        if self.run_cmd:
            opts_str = ['/usr/local/bin/openCARP'] + ['{} {}'.format(key, cmd_opts[key]) for key in cmd_opts] + \
                       ['{} ' '{}'.format(key, stim_opts[key]) for key in stim_opts]
            os.system(' '.join(opts_str))

    def interpret(self, model):
        for cmd in model.commands:
            cmd_name = cmd.__class__.__name__
            if cmd_name == "DryRun":
                self.run_cmd = False
            elif cmd_name == "SetMesh":
                self.set_mesh(cmd)
            elif cmd_name == "CreateMesh":
                self.create_mesh(cmd)
            elif cmd_name == "RegionCommand":
                self.define_region(cmd)
            elif cmd_name == "StimulusCommand":
                self.set_stimulus(cmd)
            elif cmd_name == "ParamFileCommand":
                self.param_file = cmd.param_file
            elif cmd_name == "RunCommand":
                self.run_command(cmd)
            else:
                raise CarpException('Unexpected command received: '.format(cmd_name))


def main():
    assert len(sys.argv) == 2, "Need to pass .carp file to process!"

    this_folder = os.path.dirname(__file__)

    carp_mm = metamodel_from_file(os.path.join(this_folder, 'carp_dsl.tx'), debug=False)

    # Register model processors to check inputs and flag conflicts (None identified as useful to be done as
    # preprocessor rather than during run command as yet)

    # Register object processor for CreateMesh to define default values
    obj_processors = {'CreateMesh': _preprocessor_create_mesh,
                      'RunCommand': _preprocessor_run}
    carp_mm.register_obj_processors(obj_processors)

    print("Parsing {}".format(os.path.join(this_folder, sys.argv[1])))
    example_simulation = carp_mm.model_from_file(os.path.join(this_folder, sys.argv[1]))
    # example_simulation = carp_mm.model_from_file(os.path.join(this_folder, '01_basic_usage.carp'))

    simulation = Simulation()
    simulation.interpret(example_simulation)


def _preprocessor_create_mesh(create_cmd):
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


def _preprocessor_run(run_cmd):
    # Default to monodomain if simulation type isn't specified
    if not run_cmd.sim_type:
        run_cmd.sim_type = "monodomain"

    # Provide default location to save output
    if not run_cmd.output:
        today = date.today().isoformat()

        run_cmd.output = "{}_out".format(today)
        pass


def _check_user_input(question: str, default: str = 'y'):
    """ Quickly check for user input """

    assert default.lower() == 'y' or default.lower() == 'n'
    continue_check = None

    while continue_check is None:
        continue_check = input(question) or default
        if continue_check.lower() == 'n':
            raise CarpException('Simulation aborting!')
        elif continue_check.lower() == 'y':
            pass
        else:
            continue_check = None


def get_mesh_tag_list(mesh_name):
    """ Get the list of tags present in an openCARP .elem file """
    elem = pd.read_csv(mesh_name + '.elem', sep=' ', skiprows=1, header=None)
    return elem.iloc[:, -1].unique()


def parse_param_file(filename):
    """ Parse the .par input file

    Check the options provided via the input parameter file to flag for any settings that will conflict with user
    specified commands
    """

    with open(filename, 'r') as pFile:
        lines = pFile.readlines()

    # Remove newline commands, and comment lines (start with #) and empty lines
    lines = [line.replace('\n', '') for line in lines]
    lines = [line for line in lines if not line.startswith('#')]
    lines = [line for line in lines if not line == '']

    # Split and extract the flags and their values, while removing whitespace
    lines = [line.split('=') for line in lines]
    lines = [[line_split.strip() for line_split in line] for line in lines]

    lines = [['-' + line[0], line[1]] for line in lines]
    lines_dict = dict()
    for line in lines:
        lines_dict[line[0]] = line[1]
    return lines_dict


def parse_location_command(cmd):
    if cmd.loc_units == "cm":
        loc_factor = 10000
    elif cmd.loc_units == "mm":
        loc_factor = 1000
    elif cmd.loc_units == "um":
        loc_factor = 1
    else:
        raise CarpException("Unrecognised location size")
    location = [cmd.loc_x, cmd.loc_y, cmd.loc_z]
    location = [loc * loc_factor for loc in location]

    if cmd.size_units == "cm":
        size_factor = 10000
    elif cmd.size_units == "mm":
        size_factor = 1000
    elif cmd.size_units == "um":
        size_factor = 1
    else:
        raise CarpException("Unrecognised size for size")
    size = [cmd.size_x, cmd.size_y, cmd.size_z]
    size = [s * size_factor for s in size]
    return location, loc_factor, size, size_factor


def prepare_stimulus_opts(stimulus) -> dict:
    """ Convert stimulus data into relevant strings """
    stim_dict = dict()
    for i_st, stim_data in enumerate(stimulus):
        stim_dict['-stimulus[{}].name'.format(i_st)] = '"stim"'
        stim_dict['-stimulus[{}].start'.format(i_st)] = stim_data.start
        stim_dict['-stimulus[{}].stimtype'.format(i_st)] = 0
        stim_dict['-stimulus[{}].strength'.format(i_st)] = stim_data.strength
        stim_dict['-stimulus[{}].duration'.format(i_st)] = stim_data.duration
        stim_dict['-stimulus[{}].x0'.format(i_st)] = stim_data.location[0]
        stim_dict['-stimulus[{}].xd'.format(i_st)] = stim_data.size[0]
        stim_dict['-stimulus[{}].y0'.format(i_st)] = stim_data.location[1]
        stim_dict['-stimulus[{}].yd'.format(i_st)] = stim_data.size[1]
        stim_dict['-stimulus[{}].z0'.format(i_st)] = stim_data.location[2]
        stim_dict['-stimulus[{}].zd'.format(i_st)] = stim_data.size[2]
        if stim_data.bcl is not None:
            stim_dict['-stimulus[{}].bcl'.format(i_st)] = stim_data.bcl
        if stim_data.n_pulse is not None:
            stim_dict['-stimulus[{}].npls'.format(i_st)] = stim_data.n_pulse
    return stim_dict


def check_param_conflicts(param_file, cmd_opts, stim_opts):
    """ Function to check what potential incompatibilities are present between user specified options and those given
    by a parameter file
    """
    param_opts = parse_param_file(param_file)

    repeated_keys = [True if key in cmd_opts.keys() else False for key in param_opts]

    repeated_keys = list(compress(param_opts.keys(), repeated_keys))
    warning_list = list()
    for key in repeated_keys:
        if key == '-num_stim':
            warning_list.append('Parameter file defines stimulus currents as:')
            for i_stim in range(int(param_opts['-num_stim'])):
                warning_list.append('\tCurrent {}:'.format(i_stim))
                stim_match = re.compile('-stim.*[{}]'.format(i_stim))
                matched_keys = list(filter(stim_match.match, param_opts.keys()))
                for match_key in matched_keys:
                    warning_list.append('\t\t{} = {}'.format(match_key, param_opts[match_key]))
            warning_list.append('User commands redefine stimulus as:')
            for i_stim in range(int(cmd_opts['-num_stim'])):
                warning_list.append('\tCurrent {}:'.format(i_stim))
                stim_match = re.compile('-stim.*\[{}\]'.format(i_stim))
                matched_keys = list(filter(stim_match.match, stim_opts.keys()))
                for match_key in matched_keys:
                    warning_list.append('\t\t{} = {}'.format(match_key, stim_opts[match_key]))
        if cmd_opts[key] != param_opts[key]:
            warning_list.append('Parameter file defines {} as {}, input defines it as {}'.
                                format(key, param_opts[key], cmd_opts[key]))
    if warning_list:
        for warning in warning_list:
            print(warning)
        _check_user_input('Do you wish to continue? (Y/n)')
    return None


# def get_mesh_centroid(uvc, elem):
#     """ Calculate the centroids of the elements of a mesh
#
#     I believe that openCARP calculates whether elements are activated by a region based on the centroid of that element
#     """
#
#     assert len(uvc.columns) == 4, "Make sure UVC parameters are passed to this function"
#
#     elem_val = elem.values
#
#     """ Remove region data, then reshape data """
#     elem_val_noregion = np.delete(elem_val, 4, axis=1)
#     elem_val_flat = elem_val_noregion.reshape(elem_val_noregion.size)
#
#     """ Extract centroid values, check for sign flips, then calculate means """
#     z = uvc.loc[elem_val_flat, 0].values.reshape(elem_val_noregion.shape)
#
#     rho = uvc.loc[elem_val_flat, 1].values.reshape(elem_val_noregion.shape)
#     rho_high = rho > 0.9
#     rho_high = rho_high.any(axis=1)
#     rho_low = rho < 0.1
#     rho_low = rho_low.any(axis=1)
#     rho_highlow = np.vstack([rho_high, rho_low]).transpose()
#     rho_highlow = rho_highlow.all(axis=1)
#     rho[rho_highlow] = 1
#
#     phi = uvc.loc[elem_val_flat, 2].values.reshape(elem_val_noregion.shape)
#     phi_high = phi > math.pi-0.3
#     phi_high = phi_high.any(axis=1)
#     phi_low = phi < -(math.pi-0.3)
#     phi_low = phi_low.any(axis=1)
#     phi_highlow = np.vstack([phi_high, phi_low]).transpose()
#     phi_highlow = phi_highlow.all(axis=1)
#     phi[phi_highlow] = math.pi
#
#     v = uvc.loc[elem_val_flat, 3].values.reshape(elem_val_noregion.shape)
#
#     z = np.mean(z, axis=1)
#     rho = np.mean(rho, axis=1)
#     rho[rho > 1] = 1
#     phi = np.mean(phi, axis=1)
#     v = np.mean(v, axis=1)
#     v[v != -1] = 1
#
#     print("Centroids of elements calculated.")
#
#     return np.vstack([z, rho, phi, v]).transpose()


if __name__ == "__main__":
    main()
