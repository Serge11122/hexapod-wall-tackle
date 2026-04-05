import matplotlib.pyplot as plt
import matplotlib as mpl
import torch
import torch.func
import torch.linalg

import numpy as np
from pathlib import Path
from dataclasses import dataclass

from importlib import reload

import torch_glm_2d
reload(torch_glm_2d)
from torch_glm_2d import tvec2, tquat2, torch_zero, Pose2d

from torchmin import minimize, minimize_constr


@dataclass
class Leg:
    L1, L2 = 1.0, 1.2
    mount: Pose2d
    theta1: torch.Tensor
    theta2: torch.Tensor

    def leg_poses(self):
        p0 = self.mount * Pose2d.from_angle(0, 0, self.theta1)
        p1 = p0 * Pose2d.from_angle(self.L1, 0, self.theta2)
        p2 = p1 * Pose2d.from_angle(self.L2, 0, torch_zero())
        return p2, p1, p0  # leg end returned first, then intermediate points

    def leg_end_pose(self):
        p2, p1, p0 = self.leg_poses()
        return p2


class BodyTensor:
    N_SLOTS_BODY = 3  # number of entries in tensor describing the body, currently x,y,theta
    N_SLOTS_LEG = 2  # number of entries in tensor per leg, currently theta1, theta2
    N_LEGS = 4
    N_ENTRIES = N_SLOTS_BODY + N_LEGS * N_SLOTS_LEG
    MOUNTS = [Pose2d.from_angle_no_grad(1.0, 0, 0)] * 2 + [Pose2d.from_angle_no_grad(-1.0, 0, 0)] * 2

    @staticmethod
    def zero_tensor():
        return torch.zeros(size=(BodyTensor.N_ENTRIES,))

    def __init__(self, tensor=None):
        self.tensor = self.zero_tensor() if tensor is None else tensor
        self.legs = [Leg(mount=self.MOUNTS[i],
                         theta1=self.tensor[self.N_SLOTS_BODY + i * self.N_SLOTS_LEG + 0],
                         theta2=self.tensor[self.N_SLOTS_BODY + i * self.N_SLOTS_LEG + 1])
                     for i in range(self.N_LEGS)]

    def get_body_pose(self):
        return Pose2d(p=tvec2(self.tensor[0:2]), q=tquat2.from_angle(self.tensor[2]))

    @staticmethod
    def get_lb_ub_lists():
        lb = [-10.0] * BodyTensor.N_SLOTS_BODY \
             + [-np.pi / 2.0, -np.pi] * (BodyTensor.N_LEGS // 2) \
             + [+np.pi / 2.0, -np.pi] * (BodyTensor.N_LEGS // 2)
        ub = [+10.0] * BodyTensor.N_SLOTS_BODY \
             + [1 * np.pi / 2.0, +np.pi] * (BodyTensor.N_LEGS // 2) \
             + [3 * np.pi / 2.0, +np.pi] * (BodyTensor.N_LEGS // 2)
        lb[1] = 0.0 # body_y above ground...
        lb[2] = -1.0 # keep roughly horizontal
        ub[2] = +1.0
        return lb, ub

    def __repr__(self):
        return f'BodyTensor({self.get_body_pose()=} {self.legs=})'


    def draw(self, ax, free_leg_set=[]):
        # print(f'{self.tensor=}')
        body_pose = self.get_body_pose()
        # print(f'{body_pose=}')

        w, h = tvec2(1.0, 0.0), tvec2(0.0, 0.2)
        a = (body_pose * ((w * +1.0) + (h * +1.0))).glm()
        b = (body_pose * ((w * -1.0) + (h * +1.0))).glm()
        c = (body_pose * ((w * -1.0) + (h * -1.0))).glm()
        d = (body_pose * ((w * +1.0) + (h * -1.0))).glm()
        ax.plot([a.x, b.x, c.x, d.x, a.x], [a.y, b.y, c.y, d.y, a.y], 'g-')
        for i, leg in enumerate(self.legs):
            p2, p1, p0 = [(body_pose * p_i).p.glm() for p_i in leg.leg_poses()]
            ax.plot([p0.x, p1.x], [p0.y, p1.y], 'b-')
            ax.plot([p1.x, p2.x], [p1.y, p2.y], 'r-')

            e = body_pose * leg.leg_end_pose()
            ax.plot(e.p.x, e.p.y, 'kx' if i in free_leg_set else 'ks')

            leg_end_direction = e.q.rotate_vector(tvec2(1, 0))
            ax.plot([e.p.x, e.p.x + leg_end_direction.x],
                    [e.p.y, e.p.y + leg_end_direction.y], 'r:')

        mount1 = body_pose * BodyTensor.MOUNTS[0]
        mount2 = body_pose * BodyTensor.MOUNTS[-1]
        ax.plot(mount1.p.x, mount1.p.y, 'bo')
        ax.plot(mount2.p.x, mount2.p.y, 'bo')


class Gym:
    def surface_xy(self, tau):
        # return tau, tau * 0 - 0.4
        if isinstance(tau, torch.Tensor):
            return tau, 1 / (1 + torch.exp(-(tau - 2.2) * 20)) - 0.4
        else:
            return tau, 1 / (1 + np.exp(-(tau - 2.2) * 20)) - 0.4

    def draw(self, ax):
        tau = np.linspace(-4, 6)
        x, y = self.surface_xy(tau)
        ax.plot(x, y, 'k-')
        # ax.plot([-4, 2], [-0.4, -0.4], 'k-')
        # ax.plot([2, 2], [-0.4, +0.4], 'k-')
        # ax.plot([2, 4], [+0.4, +0.4], 'k-')

def loss_fn_specific_targets(body_tensor, body_xytheta, targets):
    body = BodyTensor(body_tensor)
    body_pose = body.get_body_pose()
    # loss = 10 * torch.sum((body.get_body_pose().p - body_p).xy ** 2)
    loss = (body_tensor[0] - body_xytheta[0]) ** 2
    loss += (body_tensor[1] - body_xytheta[1]) ** 2
    loss += (body_tensor[2] - body_xytheta[2]) ** 2
    for i in range(BodyTensor.N_LEGS):
        e = body_pose * body.legs[i].leg_end_pose()
        loss += (e.p.x - targets[i].x) ** 2
        loss += (e.p.y - targets[i].y) ** 2
    return loss

class LossWithSlackAlongSurface:
    N_SLACK_VARS = 6

    def __init__(self, targets, gym):
        self.targets = targets
        self.gym = gym
        self.free_leg_set = [0, 2]

    @classmethod
    def add_slack_variables(cls, body_tensor):
        result = torch.cat([body_tensor, torch.zeros(size=(cls.N_SLACK_VARS,))])
        # Todo: we can solve or optimize for slack variables, keeping body_tensor constant as given.
        # (this way initial slack variables will be consistent with the (soft) constraints they are part of).
        with torch.no_grad():
            result[0] = -1.0
            result[1] = -1.0
            result[2] = -1.0
            result[3] = -1.0
            result[4] = 2.5
            result[5] = 2.5
        return result

    def get_lb_ub_lists(self):
        lb, ub = BodyTensor.get_lb_ub_lists()
        lb = lb + [-100] * 4 + [-100] * 2
        ub = ub + [-0.3] * 4 + [+100] * 2
        return lb, ub

    def update_targets_and_change_free_leg_set(self, body):
        body_pose = body.get_body_pose()
        for i in range(BodyTensor.N_LEGS):
            e = body_pose * body.legs[i].leg_end_pose()
            self.targets[i] = e.p

        if self.free_leg_set[0] == 0:
            self.free_leg_set = [1, 3]
        else:
            self.free_leg_set = [0, 2]


    def loss_fn(self, tensor):
        body_tensor = tensor[:-self.N_SLACK_VARS]
        slack_tensor = tensor[-self.N_SLACK_VARS:]

        body = BodyTensor(body_tensor)
        leg_end_direction_ys = slack_tensor[0:4]

        # Not elegant, but it works. fix later.
        rhos = [0] * 4
        rhos[self.free_leg_set[0]] = slack_tensor[4]
        rhos[self.free_leg_set[1]] = slack_tensor[5]

        body_pose = body.get_body_pose()
        # loss = 10 * torch.sum((body.get_body_pose().p - body_p).xy ** 2)
        loss = body_tensor[0] * 0

        # mount points above ground
        mount1 = body_pose * BodyTensor.MOUNTS[0]
        mount2 = body_pose * BodyTensor.MOUNTS[-1]
        loss += 0.2 * torch.exp(-10*mount1.p.y)
        loss += 0.2 * torch.exp(-10*mount2.p.y)

        for i in range(BodyTensor.N_LEGS):
            e = body_pose * body.legs[i].leg_end_pose()
            # ax.plot([e.p.x, e.p.x + leg_end_direction.x],
            #         [e.p.y, e.p.y + ], 'r:')
            # make slack variables equal to computed leg direction y, so we can set bounds (on the slack vars)
            leg_end_direction = e.q.rotate_vector(tvec2(1, 0))
            loss += 0.7 * (leg_end_direction.y - leg_end_direction_ys[i]) ** 2

            if i in self.free_leg_set:


                target_x, target_y = self.gym.surface_xy(rhos[i])
                loss += (e.p.x - target_x) ** 2
                loss += (e.p.y - target_y) ** 2
                loss += -target_x * 0.1
            else:
                loss += (e.p.x - self.targets[i].x) ** 2
                loss += (e.p.y - self.targets[i].y) ** 2
        return loss



def optimize_pose(loss_fn, init_tensor, lb, ub):

    x0 = init_tensor
    print(f'{x0=}')
    # f_with_jac, f_hess = _build_obj(loss, x0)
    # print(f'{f_with_jac=}')
    # fval, grad = f_with_jac(x0.detach().cpu().numpy().flatten().copy())
    # print(f'{fval=}')
    # print(f'{grad=}')
    # lb = [-1.0] * BodyTensor.N_SLOTS_BODY + [-np.pi/2.0, -np.pi] * (BodyTensor.N_LEGS//2) + [np.pi/2.0, -np.pi] * (BodyTensor.N_LEGS//2)
    # ub = [+1.0] * BodyTensor.N_SLOTS_BODY + [+np.pi/2.0, +np.pi] * (BodyTensor.N_LEGS//2) + [3*np.pi/2.0, +np.pi] * (BodyTensor.N_LEGS//2)
    # while len(lb) < init_tensor.shape[0]:
    #     lb.append(-100)
    #     ub.append(+100)

    bounds = {
        'lb': torch.tensor(lb),
        'ub': torch.tensor(ub),
    }
    res = minimize_constr(loss_fn, x0, bounds=bounds, tol=1e-5, disp=True)

    # res = minimize_constr(loss, x0, tol=1e-5, disp=True)
    # res = minimize(loss, x0, method='bfgs', tol=1e-5, disp=True)
    print(f'{res=}')
    # return BodyTensor(res.x)
    return res.x



def main():
    mpl.use('Agg')
    _, ax = plt.subplots(2, 2)
    ax = list(ax.flatten())
    print(f'{ax=}')
    for i in range(4):
        ax[i].set_aspect('equal', 'box')
        ax[i].set_xlim(-4, 8)
        ax[i].set_ylim(-6, 6)

    gym = Gym()

    body = BodyTensor()
    with torch.no_grad():
        body.tensor[0] = 0.0
        body.tensor[1] = 0.0
        body.tensor[2] = 0.0
        body.tensor[3] = -1.0
        body.tensor[4] = -1.0
        body.tensor[5] = -1.2
        body.tensor[6] = -1.0
        body.tensor[7] = 4.0
        body.tensor[8] = 1.0
        body.tensor[9] = 4.2
        body.tensor[10] = 1.0
    print(f'{body=}')
    body.draw(ax[0])

    # @memcache_noargs
    def optimize_1(init_tensor):
        lb, ub = BodyTensor.get_lb_ub_lists()
        return optimize_pose(lambda body_tensor:
                             loss_fn_specific_targets(body_tensor, body_xytheta=[0, 0, 0],
                             targets=[tvec2(+1.7, -0.4), tvec2(+1.8, -0.4), tvec2(-1.7, -0.4), tvec2(-1.8, -0.4)]),
                             init_tensor=init_tensor, lb=lb, ub=ub)
    res_x = optimize_1(init_tensor=body.tensor)
    body = BodyTensor(res_x.detach().clone())
    body.draw(ax[1])
    gym.draw(ax[1])

    loss_along_surface = LossWithSlackAlongSurface(
        targets=[tvec2(+1.7, -0.4), tvec2(+1.8, -0.4), tvec2(-1.7, -0.4), tvec2(-1.8, -0.4)],
        gym=gym)

    init_tensor_along_surface = loss_along_surface.add_slack_variables(body.tensor)
    lb, ub = loss_along_surface.get_lb_ub_lists()
    res_x = optimize_pose(loss_along_surface.loss_fn, init_tensor=init_tensor_along_surface,
                          lb=lb, ub=ub)
    body = BodyTensor(res_x[:BodyTensor.N_ENTRIES])
    body.draw(ax[2], free_leg_set=loss_along_surface.free_leg_set)
    gym.draw(ax[2])

    loss_along_surface.update_targets_and_change_free_leg_set(body)

    init_tensor_along_surface = loss_along_surface.add_slack_variables(body.tensor)
    res_x = optimize_pose(loss_along_surface.loss_fn, init_tensor=init_tensor_along_surface,
                          lb=lb, ub=ub)
    body = BodyTensor(res_x[:BodyTensor.N_ENTRIES])
    body.draw(ax[3], free_leg_set=loss_along_surface.free_leg_set)
    loss_along_surface.update_targets_and_change_free_leg_set(body)
    gym.draw(ax[3])

    output_dir = Path(__file__).parent / 'output'
    output_dir.mkdir(exist_ok=True)
    plt.tight_layout()
    plt.savefig(output_dir / 'hexapod_wall_tackle.png', dpi=150)
    print(f'Saved to {output_dir / "hexapod_wall_tackle.png"}')


if __name__ == '__main__':
    main()