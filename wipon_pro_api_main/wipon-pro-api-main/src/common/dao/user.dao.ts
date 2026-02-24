import {
  Entity,
  PrimaryGeneratedColumn,
  Column,
  CreateDateColumn,
  UpdateDateColumn,
  OneToOne,
  BaseEntity,
  OneToMany,
} from 'typeorm';
import { StoreDao } from './store.dao';
import { FeedbackMessageDao } from './feedback-message.dao';
import { Exclude } from 'class-transformer';
import { userDeviceType } from '../types/user-device.type';
import { LedgerDao } from './ledger.dao';
import { DeviceDao } from './device.dao';

@Entity('users')
export class UserDao extends BaseEntity {
  @PrimaryGeneratedColumn()
  id: number;

  @Column({ nullable: true })
  @Exclude()
  api_token: string;

  @Column()
  phone_number: string;

  @Column()
  work_phone_number: string;

  @Column()
  name: string;

  @Column()
  email: string;

  @Column()
  app_language: string;

  @Column()
  app_version: string;

  @Column({
    type: 'jsonb',
  })
  @Exclude()
  device: userDeviceType;

  @Column()
  @Exclude()
  third_party: string;

  @Column()
  @Exclude()
  user_type_id: number;

  @CreateDateColumn()
  @Exclude()
  created_at: Date;

  @UpdateDateColumn()
  @Exclude()
  updated_at: Date;

  @OneToOne(() => StoreDao, (store) => store.user)
  store: StoreDao;

  @OneToOne(() => FeedbackMessageDao, (feedback) => feedback.user)
  feedback: FeedbackMessageDao;

  @OneToOne(() => LedgerDao, (ledger) => ledger.user)
  ledger: LedgerDao;

  @OneToMany(() => DeviceDao, (device) => device.user)
  devices: DeviceDao[];

  constructor(partial: Partial<UserDao>) {
    super();
    Object.assign(this, partial);
  }
}
