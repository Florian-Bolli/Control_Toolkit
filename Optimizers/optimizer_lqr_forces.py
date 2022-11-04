"""
This is a linear-quadratic optimizer
The Jacobian of the model needs to be provided
"""

from typing import Tuple
from SI_Toolkit.computation_library import ComputationLibrary, TensorFlowLibrary

import numpy as np
import tensorflow as tf
import scipy

from Control_Toolkit.Cost_Functions.cost_function_wrapper import CostFunctionWrapper
from Control_Toolkit.Optimizers import template_optimizer
from Control_Toolkit.others.globals_and_utils import CompileTF
from SI_Toolkit.Predictors.predictor_wrapper import PredictorWrapper
from importlib import import_module

# from CartPoleSimulation.CartPole.cartpole_jacobian import cartpole_jacobian
from CartPoleSimulation.CartPole.cartpole_model import s0
from CartPoleSimulation.CartPole.state_utilities import (ANGLE_IDX, ANGLED_IDX, POSITION_IDX,
                                      POSITIOND_IDX)
from Control_Toolkit.others.globals_and_utils import create_rng


#Forces
from forces import forcespro
import numpy as np
from forces import get_userid

class optimizer_lqr_forces(template_optimizer):
    supported_computation_libraries = {TensorFlowLibrary}

    def __init__(
            self,
            predictor: PredictorWrapper,
            cost_function: CostFunctionWrapper,
            num_states: int,
            num_control_inputs: int,
            control_limits: "Tuple[np.ndarray, np.ndarray]",
            computation_library: "type[ComputationLibrary]",
            seed: int,
            mpc_horizon: int,
            optimizer_logging: bool,
            jacobian_path: str,
            action_max: float,
            P: float,
            R: float
    ):
        super().__init__(
            predictor=predictor,
            cost_function=cost_function,
            num_states=num_states,
            num_control_inputs=num_control_inputs,
            control_limits=control_limits,
            optimizer_logging=optimizer_logging,
            seed=seed,
            num_rollouts=1,
            mpc_horizon=mpc_horizon,
            computation_library=computation_library,
        )

        # self.jacobian_path = jacobian_path
        self.jacobian_module = import_module(jacobian_path)
        self.action_low = -action_max
        self.action_high = +action_max
        self.P = P
        self.R = R

        self.optimizer_reset()

        self.nx = 2
        self.nu = 1

        # Cost matrices for LQR controller
        self.Q = np.diag([self.P]*self.nx)  # How much to punish x
        self.R = np.diag([self.R]*self.nu)  # How much to punish u

        # MPC setup
        N = self.mpc_horizon
        Q = self.Q
        R = self.R
        # terminal weight obtained from discrete-time Riccati equation
        P = Q
        umin = np.array([self.action_low])
        umax = np.array([self.action_high])
        xmin = np.array([-100, -100])
        xmax = np.array([-100, 100])

        # FORCESPRO multistage form
        # assume variable ordering zi = [u{i-1}, x{i}] for i=1...N
        self.stages = forcespro.MultistageProblem(N)

        # for readability
        stages = self.stages
        nx = self.nx
        nu = self.nu

        for i in range(N):

            # dimensions
            stages.dims[i]['n'] = nx + nu  # number of stage variables
            stages.dims[i]['r'] = nx  # number of equality constraints
            stages.dims[i]['l'] = nx + nu  # number of lower bounds
            stages.dims[i]['u'] = nx + nu  # number of upper bounds

            # cost
            if (i == N - 1):
                stages.cost[i]['H'] = np.vstack(
                    (np.hstack((R, np.zeros((nu, nx)))), np.hstack((np.zeros((nx, nu)), P))))
            else:
                stages.cost[i]['H'] = np.vstack(
                    (np.hstack((R, np.zeros((nu, nx)))), np.hstack((np.zeros((nx, nu)), Q))))
            stages.cost[i]['f'] = np.zeros((nx + nu, 1))

            # lower bounds
            stages.ineq[i]['b']['lbidx'] = list(range(1, nu + nx + 1))  # lower bound acts on these indices
            stages.ineq[i]['b']['lb'] = np.concatenate((umin, xmin), 0)  # lower bound for this stage variable

            # upper bounds
            stages.ineq[i]['b']['ubidx'] = list(range(1, nu + nx + 1))  # upper bound acts on these indices
            stages.ineq[i]['b']['ub'] = np.concatenate((umax, xmax), 0)  # upper bound for this stage variable

        # solver settings
        stages.codeoptions['name'] = 'myMPC_FORCESPRO'
        stages.codeoptions['printlevel'] = 0

        # define output of the solver
        stages.newOutput('u0', 1, list(range(1, nu + 1)))




    def step(self, s: np.ndarray, time=None):

        jacobian = self.jacobian_module(s, 0.0) #linearize around u=0.0
        A = jacobian[:, :-1]
        B = np.reshape(jacobian[:, -1], newshape=(4, 1)) * self.action_high

        #for readability
        stages = self.stages
        nx = self.nx
        nu = self.nu
        N = self.mpc_horizon

        for i in range(N):
            # equality constraints
            if (i < N - 1):
                stages.eq[i]['C'] = np.hstack((np.zeros((nx, nu)), A))
            if (i > 0):
                stages.eq[i]['c'] = np.zeros((nx, 1))
            stages.eq[i]['D'] = np.hstack((B, -np.eye(nx)))

        stages.newParam('minusA_times_x0', [1], 'eq.c')  # RHS of first eq. constr. is a parameter: z1=-A*x0

        # generate code
        stages.generateCode(get_userid.userid)

        import myMPC_FORCESPRO_py
        self.problem = myMPC_FORCESPRO_py.myMPC_FORCESPRO_params
        self.A = A

        self.problem['minusA_times_x0'] = -np.dot(self.A, s)
        [solverout, exitflag, info] = self.myMPC_FORCESPRO_py.myMPC_FORCESPRO_solve(self.problem)
        if (exitflag == 1):
            u = solverout['u0']
            print('Problem solved in %5.3f milliseconds (%d iterations).' % (1000.0 * info.solvetime, info.it))
        else:
            print(info)
            raise RuntimeError('Some problem in solver')

        return u


        # state = np.array(
        #     [[s[POSITION_IDX] - self.env_mock.target_position], [s[POSITIOND_IDX]], [s[ANGLE_IDX]], [s[ANGLED_IDX]]])
        #
        # Q = np.dot(-self.K, state).item()
        #
        # Q = np.float32(Q * (1 + self.p_Q * self.rng_lqr.uniform(self.action_low, self.action_high)))
        # # Q = self.rng_lqr.uniform(-1.0, 1.0)
        #
        # # Clip Q
        # if Q > 1.0:
        #     Q = 1.0
        # elif Q < -1.0:
        #     Q = -1.0
        # else:
        #     pass

        # return Q
