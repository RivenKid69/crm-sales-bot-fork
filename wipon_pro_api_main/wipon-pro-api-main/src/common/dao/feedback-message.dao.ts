import {
  Column,
  CreateDateColumn,
  Entity,
  JoinColumn,
  OneToOne,
  PrimaryGeneratedColumn,
  UpdateDateColumn,
} from 'typeorm';
import { UserDao } from './user.dao';

@Entity('feedback_messages')
export class FeedbackMessageDao {
  @PrimaryGeneratedColumn()
  id: number;

  @Column({ name: 'user_id' })
  user_id: number;

  @Column()
  name: string;

  @Column({ name: 'phone_number' })
  phone_number: string;

  @Column()
  email: string;

  @Column({ type: 'text' })
  text: string;

  @CreateDateColumn({ name: 'created_at' })
  created_at: Date;

  @UpdateDateColumn({ name: 'updated_at' })
  updated_at: Date;

  @Column({ name: 'is_unread' })
  is_unread: boolean;

  @Column()
  photo: string;

  @Column({
    name: 'app_log',
    type: 'jsonb',
  })
  app_log: string;

  @OneToOne(() => UserDao, (user) => user.feedback)
  @JoinColumn({ name: 'user_id' })
  user: UserDao;
}
