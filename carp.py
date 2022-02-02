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
        path = os.path.join('meshes', '{}_{}'.format(today, rnd), 'block')

        create_cmd.folder = path


def set_mesh_units_preprocessor(set_cmd):
    # If no mesh units are specified, assume units are mm
    if not set_cmd.units:
        set_cmd.units = "mm"


class Simulation(object):

    def __init__(self):
        # Mesh specific commands
        self.folder = ""
        self.size = [1, 1, 1]
        self.resolution = [100, 100, 100]
        self.size_factor = 0.1
        self.resolution_factor = 1000

    def __str__(self):
        return "Mesh is saved to {}".format(self.folder)

    def interpret(self, model):
        for cmd in model.commands:
            if cmd.__class__.__name__ == "SetMesh":
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
                os.makedirs(cmd.folder)
                size = self.size*self.size_factor
                resolution = self.resolution*self.resolution_factor
                cmd_mesh = "/usr/local/bin/mesher" + \
                           " -size[0] " + str(size[0]) + \
                           " -size[1] " + str(size[1]) + \
                           " -size[2] " + str(size[2]) + \
                           " -bath[0] -0.0 -bath[1] -0.0 -bath[2] -0.0" + \
                           " -center[0] 0.0 -center[1] 0.0 -center[2] 0.0" + \
                           " -resolution[0] " + str(resolution[0]) + \
                           " -resolution[1] " + str(resolution[1]) + \
                           " -resolution[2] " + str(resolution[2]) + \
                           " -mesh " + cmd.folder + \
                           " -Elem3D 0" + \
                           " -fibers.rotEndo 0.0 -fibers.rotEpi 0.0 -fibers.sheetEndo 90.0 -fibers.sheetEpi 90.0" + \
                           " -periodic 0 -periodic_tag 1234 -perturb 0.0"
                os.system(cmd_mesh)


def main():

    this_folder = os.path.dirname(__file__)

    carp_mm = metamodel_from_file(os.path.join(this_folder, 'carp_dsl.tx'), debug=False)

    # Register object processor for CreateMesh
    carp_mm.register_obj_processors({'CreateMesh': create_mesh_preprocessor})

    basic_usage = carp_mm.model_from_file(os.path.join(this_folder, '01_basic_usage.carp'))

    simulation = Simulation()
    simulation.interpret(basic_usage)


if __name__ == "__main__":
    main()
