import gym
from datetime import datetime
from collections import deque
import numpy as np
import pdb


class Monitor:
    def __init__(
        self, monitor_param, agent_prototype, model_prototype, memory_prototype
    ):
        self.logger = monitor_param.logger
        self.logger.info("-----------------------------[ Monitor ]------------------")
        self.visualize = monitor_param.visualize
        self.env_render = monitor_param.env_render

        if self.visualize:
            self.refs = monitor_param.refs
            self.visdom = monitor_param.vis
        if self.env_render:
            self.imsave = monitor_param.imsave
            self.img_dir = monitor_param.img_dir

        self.n_episodes = monitor_param.n_episodes
        self.max_steps_in_episode = monitor_param.max_steps_in_episode
        self.eval_freq = monitor_param.eval_freq_by_episodes
        self.eval_steps = monitor_param.eval_steps

        self.seed = monitor_param.seed
        self.report_freq = monitor_param.report_freq_by_episodes
        self.reward_solved_criteria = monitor_param.reward_solved_criteria
        self.seed = monitor_param.seed

        self.logger.info("-----------------------------[ Env ]------------------")
        self.logger.info(
            f"Creating {{gym | {monitor_param.env_name}}} w/ seed {self.seed}"
        )
        self.env = gym.make(monitor_param.env_name)
        self.env.seed(self.seed)

        state_shape = self.env.observation_space.shape
        action_size = self.env.action_space.n

        self.agent = agent_prototype(
            agent_params=monitor_param.agent_params,
            state_size=state_shape,
            action_size=action_size,
            model_prototype=model_prototype,
            memory_prototype=memory_prototype,
        )

        self._reset_log()

    def _reset_log(self):
        self.summaries = {}
        for summary in [
            "steps_avg",
            "steps_std",
            "reward_avg",
            "reward_avg",
            "reward_std",
            "n_episodes_solved",
        ]:
            self.summaries[summary] = {"log": []}

        self.counter_steps = 0

    def train(self):
        self.agent.training = True
        self.logger.warning(
            "nununununununununununununu Training ... nununununununununununununu"
        )

        start_time = datetime.now()

        n_episodes_solved = 0
        rewards_window = deque(maxlen=100)
        steps_window = deque(maxlen=100)

        resolved = False

        for i_episode in range(1, self.n_episodes + 1):
            state = self.env.reset()
            episode_steps = 0
            episode_reward = 0.0

            for t in range(self.max_steps_in_episode):
                action = self.agent.act(state)
                next_state, reward, done, _ = self.env.step(action)
                self.agent.step(state, action, reward, next_state, done)
                state = next_state

                episode_reward += reward
                episode_steps += 1
                self.counter_steps += 1

                if done:
                    n_episodes_solved += 1
                    break

            self.agent.update_epsilon()
            rewards_window.append(episode_reward)
            steps_window.append(episode_steps)

            if np.mean(rewards_window) >= self.reward_solved_criteria:
                resolved = True

            self._report_log(
                i_episode,
                resolved,
                start_time,
                rewards_window,
                steps_window,
                n_episodes_solved,
            )

            # evaluation & checkpointing
            if (
                self.counter_steps > self.agent.learn_start
                and i_episode % self.eval_freq == 0
            ):
                self.logger.warning(
                    f"nununununununununununununu Evaluating @ Step {self.counter_steps}  nununununununununununununu"
                )
                self.eval_agent()

                self.agent.training = True
                self.logger.warning(
                    f"nununununununununununununu Resume Training @ Step {self.counter_steps}  nununununununununununununu"
                )

    def _report_log(
        self,
        i_episode,
        resolved,
        start_time,
        rewards_window,
        steps_window,
        n_episodes_solved,
    ):
        if i_episode % self.report_freq == 0 or resolved:
            if not resolved:
                self.logger.info(
                    f"\033[1m Reporting @ Episode {i_episode} | @ Step {self.counter_steps}"
                )
            else:
                self.logger.warning(f"Environment solved in {i_episode} episodes!")
            self.logger.info(
                f"Training Stats: elapsed time:\t{ datetime.now()-start_time}"
            )
            self.logger.info(f"Training Stats: epsilon:\t{self.agent.eps}")
            self.logger.info(f"Training Stats: avg reward:\t{np.mean(rewards_window)}")
            self.logger.info(
                f"Training Stats: avg steps by episode:\t{np.mean(steps_window)}"
            )
            self.logger.info(f"Training Stats: nepisodes_solved:\t{n_episodes_solved}")
            self.logger.info(
                f"Training Stats: repisodes_solved:\t{n_episodes_solved/self.n_episodes}"
            )

    def eval_agent(self):
        self.agent.training = False

        eval_step = 0
        eval_nepisodes_solved = 0
        eval_episode_steps = 0
        eval_episode_reward = 0
        eval_episode_reward_log = []
        eval_episode_steps_log = []

        state = self.env.reset()

        while eval_step < self.eval_steps:

            eval_action, q_values = self.agent.get_raw_actions(state)
            self.logger.debug(f"{eval_step}, state {state}, Q values {q_values}, Action {eval_action}")
            next_state, reward, done, _ = self.env.step(eval_action)
            self._render(eval_step)
            self._show_values(q_values)

            eval_episode_reward += reward
            eval_episode_steps += 1

            state = next_state

            if done:
                eval_nepisodes_solved += 1
                eval_episode_steps_log.append([eval_episode_steps])
                eval_episode_reward_log.append([eval_episode_reward])
                eval_episode_steps = 0
                eval_episode_reward = 0
                state = self.env.reset()

            eval_step += 1

        self.summaries["steps_avg"]["log"].append(
            [self.counter_steps, np.mean(eval_episode_steps_log)]
        )
        self.summaries["steps_std"]["log"].append(
            [self.counter_steps, np.std(eval_episode_steps_log)]
        )
        del eval_episode_steps_log
        self.summaries["reward_avg"]["log"].append(
            [self.counter_steps, np.mean(eval_episode_reward_log)]
        )
        self.summaries["reward_std"]["log"].append(
            [self.counter_steps, np.std(eval_episode_reward_log)]
        )
        del eval_episode_reward_log
        self.summaries["n_episodes_solved"]["log"].append(
            [self.counter_steps, eval_nepisodes_solved]
        )

        if self.visualize:
            self._visual()

        for key in self.summaries.keys():
            self.logger.info(
                f"@ Step {self.counter_steps}; {key}: {self.summaries[key]['log'][-1][1]}"
            )

    def _render(self, frame_ind):
        frame = self.env.render(mode="rgb_array")
        if self.env_render:
            frame_name = self.img_dir + f"{frame_ind:04d}.jpg"
            self.imsave(frame_name, frame)

        if self.visualize:
            self.visdom.image(
                np.transpose(frame, (2, 0, 1)),
                env=self.refs,
                win="state",
                opts=dict(title="render"),
            )

    def _show_values(self, values):
        if self.visualize:
            self.visdom.bar(
                values.T,
                env=self.refs,
                win="q_values",
                opts=dict(
                    title="q_values",
                    legend=["Nop", "left engine", "main engine", "right engine"],
                ),
            )

    def _visual(self):
        for key in self.summaries.keys():
            data = np.array(self.summaries[key]["log"])
            self.visdom.line(
                X=data[:, 0],
                Y=data[:, 1],
                env=self.refs,
                win=f"win_{key}",
                opts=dict(title=key, markers=True),
            )