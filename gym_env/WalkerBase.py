from gym_env.robot_bases import MJCFBasedRobot
# from pybullet_envs.robot_bases import MJCFBasedRobot
import numpy as np
import pybullet

# TAKEN FROM: https://github.com/bulletphysics/bullet3/blob/master/examples/pybullet/gym/pybullet_envs/robot_locomotors.py


class WalkerBase(MJCFBasedRobot):
    def __init__(self,  fn, robot_name, action_dim, obs_dim, power):
        MJCFBasedRobot.__init__(self, fn, robot_name, action_dim, obs_dim)
        self.power = power
        self.camera_x = 0
        self.start_pos_x, self.start_pos_y, self.start_pos_z = 0, 0, 0
        self.walk_target_x = 1e3  # kilometer away
        self.walk_target_y = 0
        self.body_xyz = [0, 0, 0]

    def robot_specific_reset(self, bullet_client):
        self._p = bullet_client
        for j in self.ordered_joints:
            # j.reset_current_position(
            #         self.np_random.uniform(low=-0.1, high=0.1), 0)
            j.reset_current_position(0, 0)

            # Give the robot a leg stance similar to the start of the reference motion
            if j.joint_name == 'left_hip_y':
                j.reset_current_position(0.3, 0)
            elif j.joint_name == 'right_hip_y':
                j.reset_current_position(-0.37, 0)

        # Also apply an initial force to the robot to give it some initial momentum forward
        # This should help the agent learn since the reference motion does not start from
        # a human at rest, but rather starts in the middle of a walking sequence
        self._p.applyExternalForce(self.robot_body.bodies[self.robot_body.bodyIndex], -1, [2500, 0, 50], [0, 0, -0.25], self._p.LINK_FRAME)
        # Also add a small force higher on the body to make it tilt **slightly** forward
        self._p.applyExternalForce(self.robot_body.bodies[self.robot_body.bodyIndex], -1, [380, 0, 0], [0, 0, 0.25], self._p.LINK_FRAME)

        self.feet = [self.parts[f] for f in self.foot_list]
        self.feet_contact = np.array(
            [0.0 for f in self.foot_list], dtype=np.float32)
        self.scene.actor_introduce(self)
        self.initial_z = None

    def apply_action(self, a):
        assert (np.isfinite(a).all())
        for n, j in enumerate(self.ordered_joints):
            j.set_motor_torque(self.power * j.power_coef *
                               float(np.clip(a[n], -1, +1)))

    def calc_state(self):
        j = np.array([j.current_relative_position()
                      for j in self.ordered_joints], dtype=np.float32).flatten()
        # even elements [0::2] position, scaled to -1..+1 between limits
        # odd elements  [1::2] angular speed, scaled to show -1..+1
        self.joint_speeds = j[1::2]
        self.joints_at_limit = np.count_nonzero(np.abs(j[0::2]) > 0.99)

        body_pose = self.robot_body.pose()
        parts_xyz = np.array([p.pose().xyz()
                              for p in self.parts.values()]).flatten()
        self.body_xyz = (
            parts_xyz[0::3].mean(), parts_xyz[1::3].mean(), body_pose.xyz()[2])  # torso z is more informative than mean z
        self.body_rpy = body_pose.rpy()
        z = self.body_xyz[2]
        if self.initial_z == None:
            self.initial_z = z
        r, p, yaw = self.body_rpy
        self.walk_target_theta = np.arctan2(self.walk_target_y - self.body_xyz[1],
                                            self.walk_target_x - self.body_xyz[0])
        self.walk_target_dist = np.linalg.norm(
            [self.walk_target_y - self.body_xyz[1], self.walk_target_x - self.body_xyz[0]])
        angle_to_target = self.walk_target_theta - yaw

        rot_speed = np.array(
            [[np.cos(-yaw), -np.sin(-yaw), 0],
             [np.sin(-yaw), np.cos(-yaw), 0],
             [		0,			 0, 1]]
        )
        # rotate speed back to body point of view
        vx, vy, vz = np.dot(rot_speed, self.robot_body.speed())

        more = np.array([z-self.initial_z,
                         np.sin(angle_to_target), np.cos(angle_to_target),
                         # 0.3 is just scaling typical speed into -1..+1, no physical sense here
                         0.3 * vx, 0.3 * vy, 0.3 * vz,
                         r, p], dtype=np.float32)

        return np.clip(np.concatenate([more] + [j] + [self.feet_contact]), -5, +5)

    def calc_potential(self):
                # NOTE: This is used to compute the "progress" of the humanoid. new_pot - old_pot = part of the reward
        # progress in potential field is speed*dt, typical speed is about 2-3 meter per second, this potential will change 2-3 per frame (not per second),
        # all rewards have rew/frame units and close to 1.0
        debugmode = 0
        if (debugmode):
            print("calc_potential: self.walk_target_dist")
            print(self.walk_target_dist)
            print("self.scene.dt")
            print(self.scene.dt)
            print("self.scene.frame_skip")
            print(self.scene.frame_skip)
            print("self.scene.timestep")
            print(self.scene.timestep)
        return - self.walk_target_dist / self.scene.dt
