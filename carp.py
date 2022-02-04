from datetime import date
import random
import os
import string

from textx import metamodel_from_file


def create_mesh_preprocessor(create_cmd):
    # If no folder is specified for mesh creation, put it in default location
    if not create_cmd.folder:
        today = date.today().isoformat()

        # Generate a random ASCII string
        rnd = ''.join(random.choice(string.ascii_letters) for i in range(10))

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
        self.size = [1, 1, 1]
        self.resolution = [100, 100, 100]
        self.size_factor = 0.1          # mesher expects this input to be in cm, whereas our default is mm
        self.resolution_factor = 1000   # mesher expects this input to be in um, whereas our default is mm

        # Stimulus commands
        self.n_stim = 0
        self.stim_duration = list()
        self.stim_strength = list()
        self.stim_location = list()
        self.stim_size = list()
        self.stim_factor = 1000         # mesher expects this input to be in um, whereas our default is mm

        # Parameter commands
        self.param_file = ''

    def __str__(self):
        return "Mesh is saved at {}".format(self.mesh_name)

    def interpret(self, model):
        cmd_func = os.system
        for cmd in model.commands:
            print(cmd.__class__.__name__)
            if cmd.__class__.__name__ == "DryRun":
                cmd_func = print

            elif cmd.__class__.__name__ == "SetMesh":
                if cmd.setting.lower() == "size":
                    self.size = [cmd.x, cmd.y, cmd.z]

                elif cmd.setting.lower() == "resolution":
                    self.resolution = [cmd.x, cmd.y, cmd.z]

                elif cmd.setting.lower() == "units":
                    # mesher expects size for baths, tissue, etc., to be in units of cm,
                    # while it expects the resolution to be in units of um.
                    if cmd.units == "mm":
                        self.size_factor = 0.1
                        self.resolution_factor = 100
                    elif cmd.units == "um":
                        self.size_factor = 100
                        self.resolution_factor = 1

            elif cmd.__class__.__name__ == "CreateMesh":
                print("Creating mesh...")
                if not os.path.isdir(cmd.folder):
                    os.makedirs(cmd.folder)
                size = [i_size*self.size_factor for i_size in self.size]
                resolution = [i_res*self.resolution_factor for i_res in self.resolution]
                self.mesh_name = os.path.join(cmd.folder, cmd.name)
                cmd_mesh = "/usr/local/bin/mesher" + \
                           " -size[0] " + str(size[0]) + \
                           " -size[1] " + str(size[1]) + \
                           " -size[2] " + str(size[2]) + \
                           " -bath[0] -0.0 -bath[1] -0.0 -bath[2] -0.0" + \
                           " -center[0] 0.0 -center[1] 0.0 -center[2] 0.0" + \
                           " -resolution[0] " + str(resolution[0]) + \
                           " -resolution[1] " + str(resolution[1]) + \
                           " -resolution[2] " + str(resolution[2]) + \
                           " -mesh " + str(self.mesh_name) + \
                           " -Elem3D 0" + \
                           " -fibers.rotEndo 0.0 -fibers.rotEpi 0.0 -fibers.sheetEndo 90.0 -fibers.sheetEpi 90.0" + \
                           " -periodic 0 -periodic_tag 1234 -perturb 0.0"
                print(cmd_mesh)
                cmd_func(cmd_mesh)

            elif cmd.__class__.__name__ == "StimulusCommand":
                self.n_stim = self.n_stim + 1
                self.stim_duration.append(cmd.duration)
                self.stim_strength.append(cmd.strength)
                self.stim_location.append([cmd.loc_x, cmd.loc_y, cmd.loc_z])
                self.stim_size.append([cmd.size_x, cmd.size_y, cmd.size_z])

            elif cmd.__class__.__name__ == "ParameterCommand":
                self.param_file = cmd.param_file

            elif cmd.__class__.__name__ == "RunCommand":
                if cmd.sim_type == "monodomain":
                    bidomain_flag = "0"
                elif cmd.sim_type == "bidomain":
                    bidomain_flag = "1"
                else:
                    raise Exception('Improper value passed')

                if self.param_file:
                    param_string = ' +F ./' + self.param_file
                else:
                    param_string = ''

                stim_string = ''
                for i_stim, (dur, strength, loc, size) in enumerate(zip(self.stim_duration, self.stim_strength,
                                                                        self.stim_location, self.stim_size)):
                    stim_string = stim_string +\
                                  ' -stimulus[{}].name S1'.format(i_stim) + \
                                  ' -stimulus[{}].stimtype 0'.format(i_stim) + \
                                  ' -stimulus[{}].strength {}'.format(i_stim, strength) + \
                                  ' -stimulus[{}].duration {}'.format(i_stim, dur) + \
                                  ' -stimulus[{}].x0 {}'.format(i_stim, loc[0]) + \
                                  ' -stimulus[{}].xd {}'.format(i_stim, size[0]) + \
                                  ' -stimulus[{}].y0 {}'.format(i_stim, loc[1]) + \
                                  ' -stimulus[{}].yd {}'.format(i_stim, size[1]) + \
                                  ' -stimulus[{}].z0 {}'.format(i_stim, loc[2]) + \
                                  ' -stimulus[{}].zd {}'.format(i_stim, size[2])

                carp_cmd = '/usr/local/bin/openCARP' + \
                           ' -bidomain ' + bidomain_flag +\
                           param_string + \
                           ' -ellip_use_pt 0' + \
                           ' -parab_use_pt 0' + \
                           ' -parab_options_file /usr/local/lib/python3.8/dist-packages/carputils/resources/petsc_options/ilu_cg_opts' + \
                           ' -ellip_options_file /usr/local/lib/python3.8/dist-packages/carputils/resources/petsc_options/gamg_cg_opts' + \
                           ' -simID ' + cmd.output + \
                           ' -meshname ' + self.mesh_name + \
                           ' -dt 25' + \
                           ' -tend ' + str(cmd.duration) + \
                           ' -num_phys_regions 2' + \
                           ' -phys_region[0].name "Intracellular domain"' + \
                           ' -phys_region[0].ptype 0' + \
                           ' -phys_region[0].num_IDs 1' + \
                           ' -phys_region[0].ID[0] 1' + \
                           ' -phys_region[1].name "Extracellular domain"' + \
                           ' -phys_region[1].ptype 1' + \
                           ' -phys_region[1].num_IDs 1' + \
                           ' -phys_region[1].ID[0] 1' + \
                           ' -num_stim ' + str(self.n_stim) + stim_string
                print(carp_cmd)
                cmd_func(carp_cmd)


def main():
    this_folder = os.path.dirname(__file__)

    carp_mm = metamodel_from_file(os.path.join(this_folder, 'carp_dsl.tx'), debug=False)

    # Register object processor for CreateMesh
    obj_processors = {'CreateMesh': create_mesh_preprocessor,
                      'SetMesh': set_mesh_units_preprocessor,
                      'RunCommand': run_command_preprocessor}
    carp_mm.register_obj_processors(obj_processors)

    basic_usage = carp_mm.model_from_file(os.path.join(this_folder, '01_basic_usage.carp'))

    simulation = Simulation()
    simulation.interpret(basic_usage)


if __name__ == "__main__":
    main()
