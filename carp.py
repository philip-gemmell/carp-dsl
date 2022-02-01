from datetime import date
import random
import os
import string

from textx import metamodel_from_file

from carputils import tools
from carputils import mesh


def create_mesh_preprocessor(create_cmd):
    # If no folder is specified for mesh creation, put it in default location
    if not create_cmd.folder:
        today = date.today().isoformat()

        # Generate a random ASCII string
        rnd = ''.join(random.choice(string.ascii_letters) for i in range(10))

        # Generate candidate directory name
        path = os.path.join('meshes', '{}_{}'.format(today, rnd), 'block')

        create_cmd.folder = path


def parser():
    parser = tools.standard_parser()
    # group = parser.add_argument_group('experiment specific options')
    # group.add_argument('--duration',
    #                    type=float,
    #                    default=20.,
    #                    help='Duration of simulation in [ms] (default: 20.)')
    # group.add_argument('--S1-strength',
    #                    type=float,
    #                    default=20.,
    #                    help='pick transmembrane current stimulus strength in [uA/cm^2] = [pA/pF] considering fixed Cm (default: 20.)')
    # group.add_argument('--S1-dur',
    #                    type=float,
    #                    default=2.,
    #                    help='pick transmembrane current stimulus duration in [ms] (default: 2.)')
    return parser


def jobID(args):
    """
    Generate name of top level output directory.
    """
    today = date.today()
    return '{}_basic'.format(today.isoformat())


@tools.carpexample(parser, jobID)
# @tools.carpexample(tools.standard_parser)
# @tools.standard_parser
# @tools.carpexample(tools.standard_parser, jobID)
# @tools.carpexample()
class Simulation(object):

    def __init__(self):
        # Mesh specific commands
        self.folder = ""
        self.size = [10, 10, 10]
        self.resolution = 0.1

    def __str__(self):
        return "Mesh is saved to {}".format(self.folder)

    def interpret(self, model):
        for cmd in model.commands:
            if cmd.__class__.__name__ == "SetMesh":
                if cmd.setting.lower() == "size":
                    self.size = [cmd.x, cmd.y, cmd.z]
                elif cmd.setting.lower() == "resolution":
                    self.resolution = cmd.x
            elif cmd.__class__.__name__ == "CreateMesh":
                # Block which is thin in z direction
                geom = mesh.Block(size=(self.size[0], self.size[1], self.size[2]),
                                  resolution=self.resolution)

                # Set fibre angle to 0, sheet angle to 0
                geom.set_fibres(0, 0, 90, 90)

                # Generate and return base name
                meshname = mesh.generate(geom)


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
