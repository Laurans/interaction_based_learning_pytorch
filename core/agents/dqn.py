from core.agents.agent import Agent
import random
import torch
import torch.nn.functional as F
from torch.autograd import Variable

import numpy as np
from core.memories.replaybuffer import ReplayBuffer


class MLPAgent(Agent):
    def __init__(
        self, agent_params, state_size, action_size, model_prototype, memory_prototype
    ):
        super(MLPAgent, self).__init__("MLP Agent", agent_params)

        self.action_dim = action_size
        self.model_params.state_shape = state_size
        self.model_params.action_dim = self.action_dim

        # Q-Network
        self.model = model_prototype(self.model_params).to(self.device)
        self.target_model = model_prototype(self.model_params).to(self.device)
        self.optimizer = self.optim(self.model.parameters(), lr=self.lr)

        self._update_target_model()

        # Memory
        self.memory = memory_prototype(self.memory_params)

        self.counter_steps = 0
        self.seed = random.seed(agent_params.seed)

    def step(self, state, action, reward, next_state, done):
        self.memory.append(state, action, reward, next_state, done)

        if self.counter_steps >= self.learn_start and self.counter_steps % self.learn_every == 0:
            self.learn()

        self.counter_steps += 1

    def act(self, state):
        observation = state

        if self.training and self.counter_steps < self.learn_start:
            action = random.randrange(self.action_dim)

        elif self.training and self.counter_steps >= self.learn_start:
            action = self._epsilon_greedy(observation)
        else:
            action = self._get_action(observation)

        return action

    def learn(self):
        if self.counter_steps >= self.learn_start:
            experiences = self.memory.sample(self.batch_size)
            states, actions, rewards, next_states, dones = experiences

            Q_targets_next = (
                self.target_model(next_states).detach().max(1)[0].unsqueeze(1)
            )
            Q_targets = rewards + (self.gamma * Q_targets_next * (1 - dones))

            Q_expected = self.model(states).gather(1, actions)

            loss = F.mse_loss(Q_expected, Q_targets)
            self.optimizer.zero_grad()
            loss.backward()
            self.optimizer.step()

            self._soft_update_target_model()

    def _update_target_model(self):
        self.target_model.load_state_dict(self.model.state_dict())

    def _soft_update_target_model(self):
        for target_param, local_param in zip(
            self.target_model.parameters(), self.model.parameters()
        ):
            target_param.data.copy_(
                self.tau * local_param.data + (1.0 - self.tau) * target_param.data
            )

    def update_epsilon(self):
        self.eps = max(self.eps_end, self.eps*self.eps_decay)

    def _epsilon_greedy(self, observation):
        if np.random.uniform() < self.eps:
            action = random.randrange(self.action_dim)

        else:
            action = self._get_action(observation)

        return action

    def _get_action(self, observation):
        observation = torch.from_numpy(np.array(observation)).unsqueeze(0).to(self.device)
        with torch.no_grad():
            q_values = self.model(observation).data

        if self.use_cuda:
            action = np.argmax(q_values.cpu().numpy())
        else:
            action = np.argmax(q_values.numpy())

        return action
