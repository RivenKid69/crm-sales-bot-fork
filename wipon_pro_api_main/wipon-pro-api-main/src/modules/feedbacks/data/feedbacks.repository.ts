import { EntityRepository, Repository } from 'typeorm';
import { FeedbackMessageDao } from '../../../common/dao/feedback-message.dao';

@EntityRepository(FeedbackMessageDao)
export class FeedbacksRepository extends Repository<FeedbackMessageDao> {}
