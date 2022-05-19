import argparse
import os
import pickle

import numpy as np
import matplotlib.pyplot as plt

from MADDPG import MADDPG
from util import LinearDecayParameter, get_env


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('env_name', type=str, default='adversary', help='name of the env',
                        choices=['adversary', 'crypto', 'push', 'reference', 'speaker', 'spread', 'tag',
                                 'comm'])
    parser.add_argument('--episode-num', type=int, default=500,
                        help='total episode num during training procedure')
    parser.add_argument('--learn-interval', type=int, default=100,
                        help='steps interval between learning time')
    parser.add_argument('--random-steps', type=int, default=500,
                        help='random steps before the agent start to learn')
    parser.add_argument('--update-interval', type=int, default=100,
                        help='step interval of updating target network')
    parser.add_argument('--tau', type=float, default=0.01, help='soft update parameter')
    parser.add_argument('--gamma', type=float, default=0.95, help='discount factor')
    parser.add_argument('--buffer-capacity', type=int, default=int(1e6), help='capacity of replay buffer')
    parser.add_argument('--batch-size', type=int, default=1000, help='batch-size of replay buffer')
    parser.add_argument('--actor-lr', type=float, default=0.01, help='learning rate of actor')
    parser.add_argument('--critic-lr', type=float, default=0.01, help='learning rate of critic')
    # default action space: discrete
    parser.add_argument('--continuous', action='store_true', help='set action space to continuous')
    args = parser.parse_args()

    env, env_name = get_env(args.env_name, args.continuous)
    # create folder to save result
    env_dir = os.path.join('./results', env_name)
    if not os.path.exists(env_dir):
        os.makedirs(env_dir)
    total_files = len([file for file in os.listdir(env_dir)])
    result_dir = os.path.join(env_dir, f'{total_files + 1}')
    os.makedirs(result_dir)

    env.reset()
    maddpg = MADDPG(env, args.buffer_capacity, args.batch_size, args.actor_lr, args.critic_lr)

    noise_scale = LinearDecayParameter(args.episode_num * 0.1, 0.3, args.episode_num * 0.95, 0)
    # no more noise exploration in the last 0.05 episodes

    step = 0
    agent_num = env.num_agents
    # reward of each episode of each agent
    episode_rewards = {agent: np.zeros(args.episode_num) for agent in env.agents}
    for episode in range(args.episode_num):
        maddpg.scale_noise(noise_scale(episode))  # scale noise according to current episode num
        maddpg.reset_noise()
        states = env.reset()
        agent_reward = {agent: 0 for agent in env.agents}  # agent reward of the current episode
        while env.agents:  # interact with the env for an episode
            step += 1
            if step < args.random_steps:
                actions = {agent_name: env.action_space(agent_name).sample() for agent_name in env.agents}
            else:
                actions = maddpg.select_action(states)

            next_states, rewards, dones, infos = env.step(actions)
            # env.render()

            maddpg.add(states, actions, rewards, next_states, dones)
            states = next_states

            for agent, reward in rewards.items():  # update reward
                agent_reward[agent] += reward

            # if step % args.learn_interval == 0:  # learn every few steps
            maddpg.learn(args.gamma)
            if step % args.update_interval == 0:  # update target network every few steps
                maddpg.update_target(args.tau)

        # episode finishes
        message = f'episode {episode + 1}, noise scale: {noise_scale(episode):>4f}, '
        for agent, reward in agent_reward.items():  # record reward
            episode_rewards[agent][episode] = reward
            message += f'{agent}: {reward:>4f}; '
        print(message)

    maddpg.save(result_dir)  # save model
    with open(os.path.join(result_dir, 'rewards.pkl'), 'wb') as f:  # save training data
        pickle.dump({'rewards': episode_rewards}, f)


    # training finishes, plot reward

    def get_running_reward(arr: np.ndarray, window=100):
        """calculate the running reward, i.e. average of last `window` elements from rewards"""
        running_reward = np.zeros_like(arr)
        for i in range(window - 1):
            running_reward[i] = np.mean(arr[:i + 1])
        for i in range(window - 1, len(arr)):
            running_reward[i] = np.mean(arr[i - window + 1:i + 1])
        return running_reward


    fig, ax = plt.subplots()
    x = range(1, args.episode_num + 1)
    for agent, rewards in episode_rewards.items():
        ax.plot(x, rewards, label=agent)
        ax.plot(x, get_running_reward(rewards))
    ax.legend()
    ax.set_xlabel('episode')
    ax.set_ylabel('reward')
    title = f'training result of maddpg solve {env_name}'
    ax.set_title(title)
    plt.savefig(os.path.join(result_dir, title))
