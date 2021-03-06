import gym
from datetime import datetime
from collections import deque
import numpy as np


class Monitor:
    def __init__(
        self,
        monitor_param,
        agent_prototype,
        model_prototype,
        memory_prototype,
        env_prototype,
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

        self.testing_at_end_training = monitor_param.testing

        self.train_n_episodes = monitor_param.train_n_episodes
        self.test_n_episodes = monitor_param.test_n_episodes
        self.max_steps_in_episode = monitor_param.max_steps_in_episode
        self.eval_during_training = monitor_param.eval_during_training
        self.eval_freq = monitor_param.eval_freq_by_episodes
        self.eval_steps = monitor_param.eval_steps

        self.seed = monitor_param.seed
        self.report_freq = monitor_param.report_freq_by_episodes
        self.reward_solved_criteria = monitor_param.reward_solved_criteria

        self.logger.info("-----------------------------[ Env ]------------------")
        self.logger.info(
            f"Creating {{{monitor_param.env_type} | {monitor_param.game}}} w/ seed {self.seed}"
        )

        self.env = env_prototype(monitor_param.env_params)

        state_shape = self.env.get_state_shape()
        action_size = self.env.get_action_size()

        self.output_filename = monitor_param.output_filename

        self.agent = agent_prototype(
            agent_params=monitor_param.agent_params,
            state_shape=state_shape,
            action_size=action_size,
            model_prototype=model_prototype,
            memory_prototype=memory_prototype,
        )

        self.actions_legend = monitor_param.actions_legend
        self._reset_log()

    def _reset_log(self):
        self.summaries = {}
        for summary in [
            "eval_steps_avg",
            "eval_reward_avg",
            "eval_n_episodes_solved",
            "training_rolling_reward_avg",
            "training_rolling_loss",
            "training_epsilon",
            "training_rolling_steps_avg",
            "text_elapsed_time",
            "eval_state_values",
        ]:
            if "text" in summary:
                self.summaries[summary] = {"log": "", "type": "text"}
            else:
                self.summaries[summary] = {"log": [], "type": "line"}

        self.counter_steps = 0

    def _train_on_episode(self):
        state = self.env.reset()
        episode_steps = 0
        episode_reward = 0.0
        losses = deque(maxlen=100)

        for t in range(self.max_steps_in_episode):
            action = self.agent.act(state)
            next_state, reward, done = self.env.step(action)
            self.agent.step(state, action, reward, next_state, done)

            if self.agent.t_step == 0:
                loss = self.agent.learn()
                if loss is not None:
                    losses.append(loss)

            state = next_state

            episode_reward += reward
            episode_steps += 1
            self.counter_steps += 1

            if done:
                break

        return episode_reward, episode_steps, np.mean(losses)

    def _when_resolved(self, rewards_window, i_episode, start_time, steps_window, loss):
        self._report_log_visual(
            i_episode, True, start_time, rewards_window, steps_window, loss
        )

        self.logger.info(f"+-+-+-+-+-+-+-+ Saving model ... +-+-+-+-+-+-+-+")
        self.agent.save(self.output_filename)

        self.logger.warning(
            f"nununununununununununununu Evaluating @ Step {self.counter_steps}  nununununununununununununu"
        )
        self.eval_agent()
        if self.visualize:
            self._visual()

        if self.testing_at_end_training:
            self.logger.warning(
                f"nununununununununununununu Testing Agent  nununununununununununununu"
            )
            self.test_agent()

    def train(self):
        self.agent.training = True
        self.env.training = True
        self.logger.warning(
            "nununununununununununununu Training ... nununununununununununununu"
        )

        start_time = datetime.now()

        rewards_window = deque(maxlen=100)
        steps_window = deque(maxlen=100)

        for i_episode in range(1, self.train_n_episodes + 1):

            episode_reward, episode_steps, loss = self._train_on_episode()
            self.agent.update_epsilon()

            rewards_window.append(episode_reward)
            steps_window.append(episode_steps)

            # If resolved
            if np.mean(rewards_window) >= self.reward_solved_criteria:
                self._when_resolved(
                    rewards_window, i_episode, start_time, steps_window, loss
                )
                break

            if i_episode % self.report_freq == 0:
                self._report_log_visual(
                    i_episode, False, start_time, rewards_window, steps_window, loss
                )

            # evaluation & checkpointing
            if self.eval_during_training and i_episode % self.eval_freq == 0:
                self.logger.warning(
                    f"nununununununununununununu Evaluating @ Step {self.counter_steps}  nununununununununununununu"
                )
                self.eval_agent()

                self.agent.training = True
                self.logger.warning(
                    f"nununununununununununununu Resume Training @ Step {self.counter_steps}  nununununununununununununu"
                )

                if self.visualize:
                    self._visual()

    def _report_log_visual(
        self, i_episode, resolved, start_time, rewards_window, steps_window, loss
    ):
        self.logger.info(
            f"\033[1m Reporting @ Episode {i_episode} | @ Step {self.counter_steps}"
        )

        if resolved:
            self.logger.warning(f"Environment solved in {i_episode} episodes!")
        self.logger.info(f"Training Stats: elapsed time:\t{ datetime.now()-start_time}")
        self.logger.info(f"Training Stats: epsilon:\t{self.agent.eps}")
        self.logger.info(f"Training Stats: avg reward:\t{np.mean(rewards_window)}")
        self.logger.info(
            f"Training Stats: avg steps by episode:\t{np.mean(steps_window)}"
        )
        self.logger.info(f"Training Stats: last loss:\t{loss}")

        if self.visualize:
            self.summaries["training_epsilon"]["log"].append(
                [i_episode, self.agent.eps]
            )
            self.summaries["training_rolling_reward_avg"]["log"].append(
                [i_episode, np.mean(rewards_window)]
            )
            self.summaries["training_rolling_steps_avg"]["log"].append(
                [i_episode, np.mean(steps_window)]
            )
            if loss is not None:
                self.summaries["training_rolling_loss"]["log"].append(
                    [i_episode, float(loss)]
                )

            self.summaries["text_elapsed_time"][
                "log"
            ] = f"Elapsed time \t{datetime.now()-start_time}"

            self._visual()

    def eval_agent(self):
        self.agent.training = False
        self.env.training = False

        eval_step = 0
        eval_nepisodes_solved = 0
        eval_episode_steps = 0
        eval_episode_reward = 0
        eval_episode_reward_log = []
        eval_episode_steps_log = []
        eval_state_value_log = []

        state = self.env.reset()

        while eval_step < self.eval_steps:

            state_processed = self.agent.memory.get_recent_states(state).flatten()
            eval_action, q_values = self.agent.get_raw_actions(state_processed)
            next_state, reward, done = self.env.step(eval_action)
            self.agent.memory.append_recent(state, done)
            self._render(eval_step, "eval")
            self._show_values(q_values)

            eval_state_value_log.append([eval_step, np.mean(q_values)])
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

        self.summaries["eval_steps_avg"]["log"].append(
            [self.counter_steps, np.mean(eval_episode_steps_log)]
        )
        del eval_episode_steps_log
        self.summaries["eval_reward_avg"]["log"].append(
            [self.counter_steps, np.mean(eval_episode_reward_log)]
        )
        del eval_episode_reward_log
        self.summaries["eval_n_episodes_solved"]["log"].append(
            [self.counter_steps, eval_nepisodes_solved]
        )

        self.summaries["eval_state_values"]["log"] = eval_state_value_log

        for key in self.summaries.keys():
            if self.summaries[key]["type"] == "line" and "eval" in key:
                self.logger.info(
                    f"@ Step {self.counter_steps}; {key}: {self.summaries[key]['log'][-1][1]}"
                )

    def test_agent(self, checkpoint=""):
        self.agent.training = False
        self.env.training = False
        self.agent.load(checkpoint)
        self.env_render = True
        step = 0
        for i in range(self.test_n_episodes):
            state = self.env.reset()
            done = False
            while not done:
                action = self.agent.act(state)
                next_state, reward, done = self.env.step(action)
                self._render(step, "test")
                state = next_state
                step += 1

    def _render(self, frame_ind, subdir):

        if self.env_render:
            frame = self.env.render()
            if frame is not None:
                frame_name = self.img_dir + f"{subdir}/{frame_ind:05d}.jpg"
                self.imsave(frame_name, frame)

        if self.visualize:
            frame = self.env.render()
            if frame is not None:
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
                opts=dict(title="q_values", legend=self.actions_legend),
            )

    def _visual(self):
        for key in self.summaries.keys():
            if self.summaries[key]["type"] == "line":
                data = np.array(self.summaries[key]["log"])
                if data.ndim < 2:
                    continue
                self.visdom.line(
                    X=data[:, 0],
                    Y=data[:, 1],
                    env=self.refs,
                    win=f"win_{key}",
                    opts=dict(title=key),
                )
            elif self.summaries[key]["type"] == "text":
                self.visdom.text(
                    self.summaries[key]["log"],
                    env=self.refs,
                    win=f"win_{key}",
                    opts=dict(title=key),
                )
