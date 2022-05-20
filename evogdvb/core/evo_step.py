import sys
import time
import numpy as np

from enum import Enum, auto

from pathlib import Path
from tqdm import tqdm


from .factor import Factor

from gdvb.core.verification_benchmark import VerificationBenchmark
from gdvb.plot.pie_scatter import PieScatter2D

TIME_BREAK = 10


class EvoStep:
    class Direction(Enum):
        Both = auto()
        Up = auto()
        Down = auto()

    def __init__(self, benchmark: VerificationBenchmark, evo_params: list, direction: Direction, iteration: int):
        self.benchmark = benchmark
        self.evo_params = evo_params
        self.iteration = iteration
        self.direction = direction
        self.nb_solved = None
        self.answers = None
        self.factors = self._gen_factors()

    def _gen_factors(self):
        factors = []
        for p in self.evo_params:
            start = self.benchmark.ca_configs['parameters']['range'][p][0]
            end = self.benchmark.ca_configs['parameters']['range'][p][1]
            level = self.benchmark.ca_configs['parameters']['level'][p]
            fc_conv_ids = {'fc': self.benchmark.fc_ids,
                           'conv': self.benchmark.conv_ids}
            factors += [Factor(p, start, end, level, fc_conv_ids)]
        return factors

    def forward(self):
        # launch training jobs
        self.benchmark.train()

        # wait for training
        nb_train_tasks = len(self.benchmark.verification_problems)
        progress_bar = tqdm(total=nb_train_tasks,
                            desc="Waiting on training ... ",
                            ascii=False,
                            file=sys.stdout)
        nb_trained_pre = self.benchmark.trained(True)

        progress_bar.update(nb_trained_pre)
        while not self.benchmark.trained():
            time.sleep(TIME_BREAK)
            nb_trained_now = self.benchmark.trained(True)
            progress_bar.update(nb_trained_now - nb_trained_pre)
            progress_bar.refresh()
            nb_trained_pre = nb_trained_now
        progress_bar.close()

        # analyze training results
        self.benchmark.analyze_training()

        # launch verification jobs
        self.benchmark.verify()

        # wait for verification
        nb_verification_tasks = len(self.benchmark.verification_problems)
        progress_bar = tqdm(total=nb_verification_tasks,
                            desc="Waiting on verification ... ",
                            ascii=False,
                            file=sys.stdout)

        nb_verified_pre = self.benchmark.verified(True)
        progress_bar.update(nb_verified_pre)
        while not self.benchmark.verified():
            time.sleep(TIME_BREAK)
            nb_verified_now = self.benchmark.verified(True)
            progress_bar.update(nb_verified_now - nb_verified_pre)
            progress_bar.refresh()
            nb_verified_pre = nb_verified_now
        progress_bar.close()

        # analyze verification results
        self.benchmark.analyze_verification()

    # process verification results for things
    def evaluate(self):
        benchmark = self.benchmark
        ca_configs = benchmark.ca_configs
        indexes = {}
        for p in self.evo_params:
            ids = []
            for vpc in benchmark.ca:
                ids += [vpc[x] for x in vpc if x == p]
            indexes[p] = sorted(set(ids))

        nb_property = ca_configs['parameters']['level']['prop']
        solved_per_verifiers = {}
        answers_per_verifiers = {}
        for problem in benchmark.verification_problems:
            for verifier in problem.verification_results:
                if verifier not in solved_per_verifiers:
                    shape = ()
                    for p in self.evo_params:
                        shape += (ca_configs['parameters']['level'][p],)
                    solved_per_verifiers[verifier] = np.zeros(
                        shape, dtype=np.int)
                    answers_per_verifiers[verifier] = np.empty(
                        shape+(nb_property,), dtype=np.int)
                idx = tuple(indexes[x].index(problem.vpc[x])
                            for x in self.evo_params)
                if problem.verification_results[verifier][0] in ['sat', 'unsat']:
                    solved_per_verifiers[verifier][idx] += 1
                prop_id = problem.vpc['prop']
                answer_code = benchmark.settings.answer_code[problem.verification_results[verifier][0]]
                answers_per_verifiers[verifier][idx+(prop_id,)] = answer_code

        self.nb_solved = solved_per_verifiers
        self.answers = answers_per_verifiers

    def plot(self):
        if len(self.evo_params) == 2:
            # TODO: only supports one([0]) verifier per time
            data = list(self.answers.values())[0]

            labels = self.evo_params
            ticks = [np.array(x.explicit_levels, dtype=np.float32).tolist() for x in self.factors]

            # print('XXXXXXXXXXXXXXXXX', set(sorted([np.array(x.explicit_levels).tolist() for x in self.factors][0])))
            # print('XXXXXXXXXXXXXXXXX', set(sorted([np.array(x.explicit_levels).tolist() for x in self.factors][1])))

            x_ticks = [f'{x:.4f}' for x in ticks[0]]
            y_ticks = [f'{x:.4f}' for x in ticks[1]]
            pie_scatter = PieScatter2D(data)
            pie_scatter.draw(x_ticks, y_ticks, labels[0], labels[1])
            # pdf_dir = f'./img/{list(self.answers.keys())[0]}'
            pdf_dir = f'{self.benchmark.settings.root}/figures/'
            Path(pdf_dir).mkdir(parents=True, exist_ok=True)
            pie_scatter.save(f'{pdf_dir}/{self.iteration}_{self.direction}.png')

        else:
            raise NotImplementedError

    def __str__(self) -> str:
        res = f'Iter:\t{self.iteration}'
        res += f'Dir:\t{self.direction}'
        for p in self.evo_params:
            res += f"{p}:\t{[f'{x:.3f}' for x in sorted(set([x[p] for x in self.benchmark.ca]))]}\n"
        return res