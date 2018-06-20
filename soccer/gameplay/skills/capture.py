import single_robot_behavior
import behavior
from enum import Enum
import main
import evaluation
import constants
import role_assignment
import robocup
import planning_priority
import time
import skills.move
import math


class Capture(single_robot_behavior.SingleRobotBehavior):
    # Speed in m/s at which a capture will be handled by coarse and fine approach instead of intercept
    InterceptVelocityThresh = 0.1

    # Multiplied by the speed of the ball to find a "dampened" point to move to during an intercept
    DampenMult = 0.0

    # The distance to transition from coarse approach to fine
    # TODO: The correct way to do this would be using our official max acceleration and current speed
    CoarseToFineApproachDistance = 0.3

    # the speed to have coarse approach switch from approach the ball from behind to approaching in a hook motion
    HookToDirectApproachTransisitonSpeed = 0.05

    # The distance state to avoid the ball in coarse approach
    CoarseApproachAvoidBall = 0.25

    # Minimum speed (On top of ball speed) to move towards the ball
    FineApproachMinDeltaSpeed = 0.1

    # Proportional term on the distance error between ball and robot during fine approach
    # Adds to the fine approach speed
    FineApproachDistanceMultiplier = .5

    # How much of the ball speed to add to our approach speed
    FineApproachBallSpeedMultiplier = .8

    # Time in which to wait in delay state to confirm the robot has the ball
    DelayTime = 0.5

    # Default dribbler speed, can be overriden by self.dribbler_power
    # Sets dribbler speed during intercept and fine approach
    DribbleSpeed = 0

    # The minimum dot product result between the ball and the robot to count as the ball moving at the
    # robot
    InFrontOfBallCosOfAngleThreshold = 0.3

    DelaySpeed = 0.1
    class State(Enum):
        intercept = 0
        hook_approach = 1
        coarse_approach = 2
        fine_approach = 3
        delay = 4

    ## Capture Constructor
    # faceBall - If false, any turning functions are turned off,
    # useful for using capture to reflect/bounce moving balls.
    def __init__(self, faceBall=True):
        super().__init__(continuous=False)

        # Declare all states to have a running state
        for state in Capture.State:
            self.add_state(state, behavior.Behavior.State.running)

        # State Transistions

        # Start to Intercept
        self.add_transition(
            behavior.Behavior.State.start, Capture.State.intercept,
            lambda: True, 'immediately')

        # Intercept to Hook
        self.add_transition(
            Capture.State.intercept, Capture.State.hook_approach,
            lambda: main.ball().vel.mag() < Capture.InterceptVelocityThresh or not self.bot_in_front_of_ball(),
            'Moving to capture')

        # Hook to Intercept
        self.add_transition(
            Capture.State.hook_approach, Capture.State.intercept,
            lambda: main.ball().vel.mag() >= Capture.InterceptVelocityThresh * 1.05 and self.bot_in_front_of_ball(),
            'Moving to intercept')

        # Hook to Intercept
        self.add_transition(
            Capture.State.coarse_approach, Capture.State.intercept,
            lambda: main.ball().vel.mag() >= Capture.InterceptVelocityThresh * 1.05 and self.bot_in_front_of_ball(),
            'Moving to intercept')

        # Hook to Coarse
        self.add_transition(
            Capture.State.hook_approach, Capture.State.coarse_approach,
            lambda: main.ball().vel.mag() < Capture.HookToDirectApproachTransisitonSpeed or self.find_hook_point().near_point(self.robot.pos, 0.2),
            'Moving to capture')

        # Coarse to Hook
        self.add_transition(
            Capture.State.coarse_approach, Capture.State.hook_approach,
            lambda: main.ball().vel.mag() >= Capture.HookToDirectApproachTransisitonSpeed and not self.bot_in_front_of_ball,
            'Moving to Coarse')

        # Coarse Approach to Fine
        self.add_transition(
            Capture.State.coarse_approach, Capture.State.fine_approach,
            lambda: self.bot_near_ball(Capture.CoarseToFineApproachDistance) and main.ball().valid,
            'Moving to capture')

        # Fine to Coarse Approach
        self.add_transition(
        Capture.State.fine_approach, Capture.State.coarse_approach,
            lambda: not self.bot_near_ball(Capture.CoarseToFineApproachDistance * 1.05) and main.ball().valid,
            'Lost ball during delay')

        #DELAY STATES
        self.add_transition(
            Capture.State.fine_approach, Capture.State.delay,
            lambda: evaluation.ball.robot_has_ball(self.robot),
            'has ball')

        self.add_transition(
            Capture.State.delay, Capture.State.fine_approach,
            lambda: not evaluation.ball.robot_has_ball(self.robot),
            'Lost ball during delay')

        self.add_transition(
            Capture.State.delay, behavior.Behavior.State.completed,
            lambda: time.time() - self.start_time > Capture.DelayTime and
            evaluation.ball.robot_has_ball(self.robot),
            'delay before finish')

        self.lastApproachTarget = None
        self.faceBall = faceBall

    # Helper Functions
    def bot_to_ball(self):
        return main.ball().pos - self.robot.pos

    def bot_near_ball(self, distance):
        return (self.bot_to_ball().mag() < distance)

    # Ball is moving towards us and will not stop before reaching us
    def bot_in_front_of_ball(self):
        ball2bot = self.bot_to_ball() * -1
        return (ball2bot.normalized().dot(main.ball().vel.normalized()) > Capture.InFrontOfBallCosOfAngleThreshold)
    # and ((ball2bot).mag() < (evaluation.ball.predict_stop() - main.ball().pos).mag())

    # calculates intercept point for the fast moving intercept state
    def find_intercept_point(self):
        return find_robot_intercept_point(self.robot)

    def find_hook_point(self):
        return find_robot_hook_point(self.robot)

    # returns intercept point for the slow moving capture states
    def find_coarse_point(self):
        return find_robot_coarse_point(self.robot)

    def execute_running(self):
        self.robot.set_planning_priority(planning_priority.CAPTURE)

        if (self.faceBall):
            self.robot.face(main.ball().pos)

    # sets move subbehavior
    def execute_intercept(self):
        self.robot.set_dribble_speed(Capture.DribbleSpeed)
        self.robot.disable_avoid_ball()
        pos = self.find_intercept_point()
        self.robot.move_to(pos)

    def on_enter_hook_approach(self):
        self.lastApproachTarget = None

    def execute_hook_approach(self):
        self.robot.set_dribble_speed(Capture.DribbleSpeed)
        move_point = self.find_hook_point()
        if (self.lastApproachTarget != None and (move_point - self.lastApproachTarget).mag() < 0.4):
            move_point = self.lastApproachTarget

        self.lastApproachTarget = move_point
        # don't hit the ball on accident
        if move_point.dist_to(main.ball().pos) < Capture.CoarseApproachAvoidBall + constants.Robot.Radius:
            self.robot.disable_avoid_ball()
        else:
            self.robot.set_avoid_ball_radius(Capture.CoarseApproachAvoidBall)

        self.robot.move_to(move_point)

        main.system_state().draw_circle(self.lastApproachTarget,
                                        constants.Ball.Radius,
                                        constants.Colors.White, "Capture")

    def on_exit_hook_approach(self):
        self.lastApproachTarget is None

    def on_enter_coarse_approach(self):
        self.lastApproachTarget = None

    def execute_coarse_approach(self):
        self.robot.set_dribble_speed(Capture.DribbleSpeed)
        move_point = self.find_coarse_point()
        if (self.lastApproachTarget != None and (move_point - self.lastApproachTarget).mag() < 0.3):
            move_point = self.lastApproachTarget

        self.lastApproachTarget = move_point
        # don't hit the ball on accident
        if move_point.dist_to(main.ball().pos) < Capture.CoarseApproachAvoidBall + constants.Robot.Radius:
            self.robot.disable_avoid_ball()
        else:
            self.robot.set_avoid_ball_radius(Capture.CoarseApproachAvoidBall)

        self.robot.move_to(move_point)

        main.system_state().draw_circle(self.lastApproachTarget,
                                        constants.Ball.Radius,
                                        constants.Colors.White, "Capture")

    def on_exit_coarse_approach(self):
        self.lastApproachTarget is None

    def execute_fine_approach(self):
        self.robot.disable_avoid_ball()
        self.robot.set_dribble_speed(Capture.DribbleSpeed)

        bot2ball_dir = (main.ball().pos - self.robot.pos).normalized()
        approach = self.bot_to_ball() * Capture.FineApproachDistanceMultiplier + \
                    bot2ball_dir * Capture.FineApproachMinDeltaSpeed + \
                    main.ball().vel * Capture.FineApproachBallSpeedMultiplier
        if (approach.mag() > 1):
            approach = approach.normalized() * 1
        self.robot.set_world_vel(approach)

    def on_enter_delay(self):
        self.start_time = time.time()

    def execute_delay(self):
        self.robot.disable_avoid_ball()
        self.robot.set_dribble_speed(Capture.DribbleSpeed)

        ball_dir = (main.ball().pos - self.robot.pos).normalized()
        if main.ball().vel.mag() < Capture.DelaySpeed:
            self.robot.set_world_vel(ball_dir*Capture.DelaySpeed)
        elif main.ball().vel.mag() < Capture.DelaySpeed:
            delay_speed = main.ball().vel.mag() - Capture.DelaySpeed
            self.robot.set_world_vel(ball_dir*delay_speed)
        self.robot.face(main.ball().pos)

    def role_requirements(self):
        reqs = super().role_requirements()
        reqs.require_kicking = True

        for r in role_assignment.iterate_role_requirements_tree_leaves(reqs):
            if main.ball().valid:
                if self.state == Capture.State.intercept:
                    reqs.cost_func = lambda r: robocup.Line(main.ball().pos, main.ball().pos + main.ball().vel * 10).dist_to(r.pos)
                else:
                    reqs.cost_func = lambda r: main.ball().pos.dist_to(r.pos)
        return reqs

# Robot based helper functions
# calculates intercept point for the fast moving intercept state
def find_robot_intercept_point(robot):
    if (robot is not None):
        passline = robocup.Line(main.ball().pos, main.ball().pos + main.ball().vel * 10)
        pos = passline.nearest_point(robot.pos) + (main.ball().vel * Capture.DampenMult)
        return pos
    else:
        return None

# Finds a point ahead of the ball and to the right or left of it if the ball velocity is above the threshold. Otherwise returns ball position
def find_robot_hook_point(robot):
    pos = main.ball().pos + main.ball().vel * 1.4
    move_point = pos + main.ball().vel * 0.2
    angle = pos.normalized().cross(robot.pos.normalized())
    if angle < 0.05:
        move_point.rotate(pos, math.pi/2)
    elif angle > -0.05:
        move_point.rotate(pos, -1 * (math.pi/2))
    else:
        move_point.rotate(pos, -1 * (math.pi/2))

    return move_point

def find_robot_coarse_point(robot):
    return main.ball().pos

# calculates capture point for the slow or stationary fine approach state
def find_robot_capture_point(robot):
    if robot is None:
        return main.ball().pos

    approach_vec = approach_vector(robot)
    # sample every 5 cm in the -approach_vector direction from the ball
    pos = None

    for i in range(50):
        dist = i * 0.05
        pos = main.ball().pos + main.ball().vel + approach_vec * dist
        # how long will it take the ball to get there
        ball_time = evaluation.ball.rev_predict(dist)
        robotDist = (pos - robot.pos).mag() * 0.6
        bot_time = robocup.get_trapezoidal_time(robotDist, robotDist, 2.2, 1,
                                                robot.vel.mag(), 0)

        if bot_time < ball_time:
            break

    return pos

def approach_vector(robot):
    if main.ball().vel.mag() > 0.05:
        # ball's moving, get on the side it's moving towards
        return main.ball().vel.normalized()
    else:
        return (robot.pos - main.ball().pos).normalized()
