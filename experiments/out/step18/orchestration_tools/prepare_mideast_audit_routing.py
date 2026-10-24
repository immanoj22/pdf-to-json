"""Independent audit routing; leave the queued robustness input capture untouched."""
import json
from evaluation_routes import BASE, finished, sha, write_new
import prepare_visual_populations as populations
import render_selected_targets as renders

def main():
    finished()
    performance_path = BASE / 'mideast_attempt1/performance.json'
    performance = json.loads(performance_path.read_text('utf8'))
    run = performance['run']
    def actual_run_without_input_copy(book):
        assert book == 'mideast'
        return run, BASE / 'evaluations/mideast/inputs', dict(run['cache_keys'])
    # Only supply the actual run identity: the normal route's copied performance
    # file belongs to the later queued robustness job. Population, sample and
    # rendering implementations remain exactly the already recorded helpers.
    populations.route = actual_run_without_input_copy
    renders.route = actual_run_without_input_copy
    write_new(BASE / 'audit/mideast/audit_routing_receipt.json', {
        'book_id': 'mideast', 'performance_sha256': sha(performance_path),
        'helper_sha256': {name: sha(BASE / name) for name in (
            'prepare_visual_populations.py', 'render_selected_targets.py', 'fixed_sampling.py')},
        'routing_only': 'Read actual performance directly without writing the queued robustness input copy.',
        'scoring_or_sampling_algorithm_changed': False,
        'converter_rerun': False, 'reference_accuracy_claim': False})
    populations.main('mideast')
    renders.main('mideast')

if __name__ == '__main__':
    main()
